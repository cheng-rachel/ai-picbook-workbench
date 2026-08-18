"""Deterministic Level 2 Draft validation; it reports and never rewrites text."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

from .repository import normalize_lemma, textbook_lookup_forms
from .services import HistoricalVocabularyService, ReferenceDataService

RULE_VERSION = "PU2-V1.0"
ALLOWED_PAGE_COUNTS = {8, 12}
ORIENTATIONS = {"STORY", "LANGUAGE", "BALANCED"}

# Script-style dialogue line, e.g. "Big Elephant: You can't use your hands."
# The leading "Name:" is a speaker label (a structural marker for future speech
# bubbles), not prose: it is excluded from word/sentence metrics and from the
# vocabulary scan. Matches at line starts and after sentence-ending punctuation.
SPEAKER_LABEL_RE = re.compile(
    r"(?m)(?:^|(?<=[.!?]))[ \t]*((?:[A-Z][A-Za-z'’]*)(?:[ \t]+[A-Z][A-Za-z'’]*){0,2}):[ \t]*")

# Function words are not teaching-role candidates in the lightweight V1 scan.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "so", "because", "if", "then", "than",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their", "this", "that", "these", "those",
    "is", "am", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "can", "could", "will", "would", "shall", "should", "may",
    "might", "must", "to", "of", "in", "on", "at", "by", "for", "from", "with",
    "into", "onto", "over", "under", "up", "down", "out", "off", "as", "not", "no",
    "yes", "very", "too", "also", "there", "here", "what", "where", "when", "who",
    "why", "how", "many", "more", "again", "now", "just", "only", "all", "some",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "im", "ill", "dont", "doesnt", "didnt", "cant", "couldnt", "wont", "lets",
}


def normalize_phrase(value: str) -> str:
    value = value.lower().replace("’", "'")
    return " ".join(re.findall(r"[a-z]+(?:'[a-z]+)?|\d+", value))


def word_tokens(text: str) -> list[str]:
    return [token.lower().replace("’", "'")
            for token in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+", text)]


def surface_word_tokens(text: str) -> list[str]:
    return [token.replace("’", "'")
            for token in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+", text)]


def content_hash(pages: list[dict]) -> str:
    canonical = "\n".join(f"{page['page_number']}:{page.get('text', '')}" for page in
                           sorted(pages, key=lambda item: item["page_number"]))
    return sha256(canonical.encode("utf-8")).hexdigest()


def _phrase_spans(tokens: list[str], phrase: str) -> list[tuple[int, int]]:
    target = word_tokens(phrase)
    if not target:
        return []
    size = len(target)
    return [(index, index + size) for index in range(len(tokens) - size + 1)
            if tokens[index:index + size] == target]


def _sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"[.!?]+(?:[\"'”’]+)?", text)
            if sentence.strip()]


def split_speaker_labels(text: str) -> tuple[str, list[str]]:
    """Strip script-style speaker labels; return the prose text and label names."""
    names: list[str] = []

    def _capture(match: re.Match) -> str:
        names.append(match.group(1))
        return ""

    return SPEAKER_LABEL_RE.sub(_capture, text), names


class DraftValidator:
    def __init__(self, reference: ReferenceDataService,
                 history: HistoricalVocabularyService):
        self.reference = reference
        self.history = history

    @staticmethod
    def _issue(issues: list[dict], rule_key: str, severity: str, scope: dict,
               message: str, resolution_options: list[str] | None = None) -> None:
        issues.append({"rule_key": rule_key, "severity": severity, "scope": scope,
                       "message": message, "resolution_options": resolution_options or []})

    def _source_status(self, raw_form: str, textbook_words: set[str]) -> tuple[str, str]:
        """TEXTBOOK = current unit words; TEXTBOOK_SCOPE = other Power Up 2 units.

        The former curriculum-vocabulary source no longer exists in 01docs, so
        the whole Power Up 2 word scope is the only "already taught" lookup.
        """
        normalized = normalize_phrase(raw_form)
        lemma = normalize_lemma(normalized)
        if normalized in textbook_words:
            return "TEXTBOOK", lemma
        scope_hits = self.reference.lookup_textbook_entry(raw_form)
        return ("TEXTBOOK_SCOPE" if scope_hits else "UNRESOLVED"), lemma

    def validate(self, pages: list[dict], plan: dict, topic: dict,
                 confirmed_vocabulary: dict[tuple[str, str], dict] | None = None) -> dict:
        confirmed_vocabulary = confirmed_vocabulary or {}
        issues: list[dict] = []
        sorted_pages = sorted(pages, key=lambda page: page["page_number"])
        page_count = len(sorted_pages)
        target_page_count = plan["page_count"]
        page_numbers = [page["page_number"] for page in sorted_pages]
        if page_count not in ALLOWED_PAGE_COUNTS or page_count != target_page_count or \
                page_numbers != list(range(1, page_count + 1)):
            self._issue(issues, "VAL-PAGE-001", "BLOCKER", {"type": "book"},
                        f"Expected exactly pages 1–{target_page_count}; received {page_numbers}.")

        sentence_metrics = []
        all_tokens: list[str] = []
        all_surfaces: list[str] = []
        all_sentence_initial: list[bool] = []
        speaker_label_names: set[str] = set()
        prose_by_page: dict[int, str] = {}
        for page in sorted_pages:
            text = page.get("text", "")
            prose, labels = split_speaker_labels(text)
            prose_by_page[page["page_number"]] = prose
            for label in labels:
                speaker_label_names.update(normalize_phrase(token)
                                           for token in word_tokens(label))
            if not text.strip():
                self._issue(issues, "VAL-BLANK-PAGE-001", "BLOCKER",
                            {"type": "page", "page_number": page["page_number"]},
                            "Page is blank.")
                sentences = []
            else:
                sentences = _sentences(prose)
                if len(sentences) < 2 or len(sentences) > 3:
                    self._issue(issues, "VAL-PAGE-SENT-001", "WARNING",
                                {"type": "page", "page_number": page["page_number"]},
                                f"Page has {len(sentences)} sentences; target is 2–3.")
            sentence_counts = []
            for sentence_number, sentence in enumerate(sentences, 1):
                count = len(word_tokens(sentence))
                sentence_counts.append(count)
                if count > 10:
                    self._issue(issues, "VAL-SENT-LEN-001", "WARNING",
                                {"type": "sentence", "page_number": page["page_number"],
                                 "sentence_number": sentence_number},
                                f"Sentence has {count} words; target is 10 or fewer.")
            sentence_metrics.append({"page_number": page["page_number"],
                                     "sentence_count": len(sentences),
                                     "sentence_word_counts": sentence_counts})
            for sentence in sentences:
                surfaces = surface_word_tokens(sentence)
                all_surfaces.extend(surfaces)
                all_tokens.extend(token.lower() for token in surfaces)
                all_sentence_initial.extend(index == 0 for index in range(len(surfaces)))
            # Prevent a multiword item or Pattern from matching across a page boundary.
            all_tokens.append("__page_break__")
            all_surfaces.append("__page_break__")
            all_sentence_initial.append(False)

        total_word_count = sum(1 for token in all_tokens if token != "__page_break__")
        if total_word_count < 120 or total_word_count > 200:
            self._issue(issues, "VAL-WORDCOUNT-001", "WARNING", {"type": "book"},
                        f"Total word count is {total_word_count}; target is 120–200.")

        planned_vocab = plan.get("planned_vocabulary", [])
        planned_patterns = plan.get("planned_core_patterns", [])
        textbook_words = {normalize_phrase(form)
                          for form in textbook_lookup_forms(topic["textbook_words"])}
        covered_token_indices: set[int] = set()
        vocab_observations = []
        role_counts = Counter()
        history_conflicts = []

        for item in planned_vocab:
            spans = _phrase_spans(all_tokens, item["raw_form"])
            for start, end in spans:
                covered_token_indices.update(range(start, end))
            target_tokens = word_tokens(item["raw_form"])
            inherited_indices: set[int] = set()
            if len(target_tokens) == 1 and item.get("teacher_confirmed"):
                planned_lemma = item.get("lemma") or normalize_lemma(target_tokens[0])
                inherited_indices = {
                    index for index, token in enumerate(all_tokens)
                    if token != "__page_break__" and normalize_lemma(token) == planned_lemma
                }
                covered_token_indices.update(inherited_indices)
            count = len(inherited_indices) if inherited_indices else len(spans)
            role = item["role"]
            role_counts[role] += 1
            status, lemma = self._source_status(item["raw_form"], textbook_words)
            historical = self.history.get_historical_vocab_usage(lemma, topic["level_id"])
            conflict = role in {"CORE", "EXTENSION"} and any(
                record["historical_role"] in {"CORE", "EXTENSION", "EXTENSION_THEME",
                                                "EXTENSION_CULTURAL"}
                for record in historical)
            if conflict:
                history_conflicts.append({"raw_form": item["raw_form"], "lemma": lemma,
                                          "historical_usage": historical})
                self._issue(issues, "VAL-HISTORY-001", "WARNING",
                            {"type": "word", "word": item["raw_form"]},
                            "Planned word conflicts with a historical Final role.",
                            ["review history", "acknowledge", "replace", "remove"])
            if status == "UNRESOLVED":
                self._issue(issues, "VAL-VOCAB-SOURCE-001", "WARNING",
                            {"type": "word", "word": item["raw_form"]},
                            "Word is outside the Power Up 2 textbook word scope.",
                            ["manual review", "remove", "retain with note"])
            if role == "CORE":
                if count == 0:
                    self._issue(issues, "VAL-CORE-001", "WARNING",
                                {"type": "word", "word": item["raw_form"]},
                                "Planned core word does not appear.")
                if count < 3 or count > 5:
                    self._issue(issues, "VAL-CORE-FREQ-001", "WARNING",
                                {"type": "word", "word": item["raw_form"]},
                                f"Core word appears {count} times; target is about 3–5.")
            elif role == "EXTENSION" and count == 0:
                self._issue(issues, "VAL-EXT-001", "WARNING",
                            {"type": "word", "word": item["raw_form"]},
                            "Planned extension word does not appear.",
                            ["remove from plan", "add naturally"])
            elif role == "REVIEW" and count == 0:
                pool_size = plan.get("review_candidates", {}).get("pool_size", 0)
                severity = "WARNING" if pool_size >= 5 else "INFO"
                self._issue(issues, "VAL-REVIEW-001", severity,
                            {"type": "word", "word": item["raw_form"]},
                            "Planned review word does not appear.")
            vocab_observations.append({
                "raw_form": item["raw_form"], "normalized_form": normalize_phrase(item["raw_form"]),
                "lemma": lemma, "token_count": count, "planned_role": role,
                "detected_status": "PLANNED", "source_lookup_status": status,
                "classification_state": "PLANNED",
                "textbook_source_hit": status == "TEXTBOOK",
                # Schema-stable column, now meaning "hit in another Power Up 2 unit".
                "curriculum_source_hit": status == "TEXTBOOK_SCOPE",
                "historical_conflict_hit": conflict,
                "manual_review_required": status == "UNRESOLVED",
            })

        if role_counts["EXTENSION"] > 4:
            self._issue(issues, "VAL-EXT-COUNT-001", "WARNING", {"type": "book"},
                        f"Plan contains {role_counts['EXTENSION']} extension words; reference maximum is 4.")
        if role_counts["NON_TEACHING_CONTEXT"] > 5:
            self._issue(issues, "VAL-NON-TEACHING-001", "WARNING", {"type": "book"},
                        f"Plan contains {role_counts['NON_TEACHING_CONTEXT']} non-teaching context words; target maximum is 5.")
        pool_size = plan.get("review_candidates", {}).get("pool_size", 0)
        if pool_size >= 5 and role_counts["REVIEW"] not in {5, 6}:
            self._issue(issues, "VAL-REVIEW-COUNT-001", "WARNING", {"type": "book"},
                        f"Review pool has {pool_size} words; planned count target is 5–6.")

        # Core Patterns are already teacher-confirmed teaching units. Their exact
        # token spans must not be presented again as independent vocabulary work.
        for pattern in planned_patterns:
            raw = pattern["raw_pattern"] if isinstance(pattern, dict) else str(pattern)
            for start, end in _phrase_spans(all_tokens, raw):
                covered_token_indices.update(range(start, end))

        capitalized_counts = Counter()
        capitalized_non_initial = set()
        for surface, token, sentence_initial in zip(
                all_surfaces, all_tokens, all_sentence_initial):
            if token == "__page_break__" or not surface[:1].isupper():
                continue
            normalized = normalize_phrase(token)
            capitalized_counts[normalized] += 1
            if not sentence_initial:
                capitalized_non_initial.add(normalized)
        # Narrow character-label heuristic only: repeated capitalization plus at
        # least one non-sentence-initial occurrence. This is not general NER.
        # Names taken from script-style speaker labels are authoritative and are
        # added directly, since those labels are always line-initial.
        explicit_character_names = {
            token for token, count in capitalized_counts.items()
            if count >= 2 and token in capitalized_non_initial
        } | speaker_label_names

        unplanned = Counter()
        for index, token in enumerate(all_tokens):
            if token == "__page_break__":
                continue
            normalized = normalize_phrase(token)
            function_key = normalized.replace("'", "")
            possessive_base = normalized[:-2] if normalized.endswith("'s") else None
            character_name = normalized in explicit_character_names or \
                possessive_base in explicit_character_names
            if index not in covered_token_indices and function_key not in FUNCTION_WORDS and \
                    not character_name and not normalized.isdigit():
                unplanned[normalize_lemma(normalized)] += 1
        unresolved_needing_review = []
        classification_counts = Counter({"PLANNED": len(vocab_observations)})
        for lemma, count in sorted(unplanned.items()):
            status, canonical = self._source_status(lemma, textbook_words)
            classification_state = ("KNOWN_UNPLANNED" if status in {
                "TEXTBOOK", "TEXTBOOK_SCOPE"
            } else "NEEDS_REVIEW")
            confirmation = confirmed_vocabulary.get((lemma, canonical), {})
            teacher_confirmed = bool(confirmation.get("teacher_confirmed"))
            confirmed_role = confirmation.get("confirmed_role") if teacher_confirmed else None
            needs_manual_review = classification_state == "NEEDS_REVIEW" and not teacher_confirmed
            classification_counts[classification_state] += 1
            if needs_manual_review:
                unresolved_needing_review.append(lemma)
            vocab_observations.append({
                "raw_form": lemma, "normalized_form": lemma, "lemma": canonical,
                "token_count": count, "planned_role": None,
                "detected_status": "UNCLASSIFIED", "source_lookup_status": status,
                "classification_state": classification_state,
                "confirmed_role": confirmed_role,
                "teacher_confirmed": teacher_confirmed,
                "textbook_source_hit": status == "TEXTBOOK",
                "curriculum_source_hit": status == "TEXTBOOK_SCOPE",
                "historical_conflict_hit": False,
                "manual_review_required": needs_manual_review,
            })
        if unresolved_needing_review:
            self._issue(issues, "VAL-UNCLASSIFIED-001", "BLOCKER", {"type": "book"},
                        f"{len(unresolved_needing_review)} unresolved content-word lemmas require teacher review.",
                        ["classify vocabulary", "mark non-teaching context", "ignore function/proper name"])

        pattern_observations = []
        if len(planned_patterns) < 1 or len(planned_patterns) > 2:
            self._issue(issues, "VAL-PATTERN-001", "WARNING", {"type": "book"},
                        f"Plan has {len(planned_patterns)} core patterns; target is 1–2.")
        for pattern in planned_patterns:
            raw = pattern["raw_pattern"] if isinstance(pattern, dict) else str(pattern)
            spans = _phrase_spans(all_tokens, raw)
            matched_pages = [page["page_number"] for page in sorted_pages
                             if _phrase_spans(word_tokens(prose_by_page[page["page_number"]]), raw)]
            count = len(spans)
            if count < 3 or count > 5:
                self._issue(issues, "VAL-PATTERN-002", "WARNING",
                            {"type": "pattern", "pattern": raw},
                            f"Core pattern appears {count} times; target is about 3–5.")
            pattern_observations.append({"target_pattern": raw,
                                         "normalized_pattern": normalize_phrase(raw),
                                         "matched_count": count,
                                         "matched_pages": matched_pages,
                                         "manual_review_required": False})

        severities = Counter(issue["severity"] for issue in issues)
        overall = "BLOCKED" if severities["BLOCKER"] else "WARNING" if severities["WARNING"] else "PASS"
        return {
            "overall_status": overall,
            "summary": dict(severities),
            "issues": issues,
            "metrics": {
                "page_count": page_count, "target_page_count": target_page_count,
                "total_word_count": total_word_count, "page_sentences": sentence_metrics,
                "planned_role_counts": dict(role_counts),
                "classification_state_counts": dict(classification_counts),
                "unclassified_content_word_count": len(unresolved_needing_review),
                "needs_review_unconfirmed_count": len(unresolved_needing_review),
                "historical_conflict_count": len(history_conflicts),
            },
            "content_hash": content_hash(sorted_pages), "rule_version": RULE_VERSION,
            "vocabulary_observations": vocab_observations,
            "pattern_observations": pattern_observations,
        }
