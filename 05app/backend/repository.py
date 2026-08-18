from __future__ import annotations

import json
from pathlib import Path

from .config import DATABASE_PATH
from .database import connect
from .extractors import normalize

IRREGULAR_LEMMAS = {
    "children": "child", "went": "go", "feet": "foot", "men": "man",
    "women": "woman", "mice": "mouse", "goes": "go", "does": "do",
    "has": "have",
}


def normalize_lemma(value: str) -> str:
    form = normalize(value)
    if form in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[form]
    # Apostrophe forms are contractions/possessives, not plural or third-person
    # suffixes. In particular, never turn "let's" into the artifact "let'".
    if "'" in form or "’" in form:
        return form.replace("’", "'")
    if form.endswith("ies") and len(form) > 3:
        return form[:-3] + "y"
    if form.endswith("e"):
        return form
    if form.endswith(("ches", "shes", "xes", "zes", "sses")) and len(form) > 4:
        return form[:-2]
    if form.endswith("s") and not form.endswith(("ss", "is", "us")) and len(form) > 2:
        return form[:-1]
    return form


def expand_entry_alternatives(raw_entry: str) -> list[str]:
    """Expand token-wise slash alternatives without rewriting the source entry.

    "leaf/leaves" -> ["leaf", "leaves"]; "clean/brush your teeth" ->
    ["clean your teeth", "brush your teeth"]. Entries without "/" pass through.
    """
    tokens = raw_entry.split()
    options = [token.split("/") if "/" in token else [token] for token in tokens]
    combos: list[list[str]] = [[]]
    for alternatives in options:
        combos = [combo + [alt] for combo in combos
                  for alt in alternatives if alt]
        if len(combos) > 8:  # defensive cap; source entries are tiny
            break
    return [" ".join(combo) for combo in combos] or [raw_entry]


def textbook_lookup_forms(entries: list[str]) -> set[str]:
    """Normalized lookup forms for textbook entries, including slash variants."""
    forms: set[str] = set()
    for entry in entries:
        for alternative in expand_entry_alternatives(entry):
            normalized = normalize(alternative)
            if normalized:
                forms.add(normalized)
    return forms


class ReferenceRepository:
    def __init__(self, database_path: Path = DATABASE_PATH):
        self.database_path = Path(database_path)

    def get_topic(self, topic_id: str | int) -> dict | None:
        key = f"L2-T{int(topic_id):02d}" if str(topic_id).isdigit() else str(topic_id)
        with connect(self.database_path) as db:
            row = db.execute("SELECT * FROM topics WHERE topic_id=? AND active=1", (key,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["textbook_words"] = [r[0] for r in db.execute("SELECT raw_entry FROM textbook_words WHERE topic_id=? ORDER BY sequence_no", (key,))]
            result["textbook_structures"] = [r[0] for r in db.execute("SELECT raw_structure FROM textbook_structures WHERE topic_id=? ORDER BY sequence_no", (key,))]
            result["textbook_examples"] = [dict(r) for r in db.execute("SELECT raw_sentence,source_section,verification_status FROM textbook_examples WHERE topic_id=? ORDER BY example_id", (key,))]
            return result

    def get_level_rules(self, level_id: int) -> dict:
        with connect(self.database_path) as db:
            rows = db.execute("SELECT rule_key,effective_value_json,rule_strength,raw_value,source_section FROM level_rules WHERE level_id=?", (level_id,))
            return {row["rule_key"]: {"effective_value": json.loads(row["effective_value_json"]), "rule_strength": row["rule_strength"], "raw_value": row["raw_value"], "source_section": row["source_section"]} for row in rows}

    def lookup_textbook_entry(self, word: str) -> list[dict]:
        """Exact lookup across ALL Power Up 2 unit words (the coursebook scope).

        This replaces the former curriculum-vocabulary lookup: with the
        curriculum source removed from 01docs, the Power Up 2 textbook word
        scope is the only authoritative "already taught/known" source.
        """
        form = normalize(word)
        lemma = normalize_lemma(form)
        results = []
        with connect(self.database_path) as db:
            rows = db.execute("""
                SELECT w.raw_entry, w.normalized_entry, w.entry_type,
                       w.topic_id, t.unit_number, t.unit_title
                FROM textbook_words w JOIN topics t ON t.topic_id=w.topic_id
                WHERE t.active=1 ORDER BY t.unit_number, w.sequence_no
            """).fetchall()
        for row in rows:
            match_type = None
            for alternative in expand_entry_alternatives(row["raw_entry"]):
                alt_form = normalize(alternative)
                if alt_form == form:
                    match_type = "exact"
                    break
                if " " not in alt_form and normalize_lemma(alt_form) == lemma:
                    match_type = "lemma"
                    break
            if match_type:
                item = dict(row)
                item.update({"query_raw": word, "normalized_form": form,
                             "lemma": lemma, "match_type": match_type})
                results.append(item)
        return results
