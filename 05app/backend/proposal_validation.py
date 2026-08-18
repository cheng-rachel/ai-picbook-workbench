"""Lightweight Proposal validation and repeatable evaluation metrics."""

from __future__ import annotations

from collections import Counter
import re

from .proposal_schema import CANONICAL_BOOK_TYPES, REQUIRED_PROPOSAL_FIELDS
from .repository import textbook_lookup_forms
from .services import ReferenceDataService

STORYLINE_SECTION_LABEL = re.compile(
    r"(?:^|[。！？!?\s])(?:起因|发展|核心问题(?:或目标)?|主要循环(?:或转折)?|转折|解决(?:或结尾)?|结尾)\s*[：:]"
)

DIAGNOSTIC_PATTERNS = {
    "repeated_plot_driver": {
        "task_or_challenge": r"任务|闯关|挑战|比赛|清单",
        "count_or_record": r"计数|数到|记录|表格",
        "repeated_attempt": r"再试|重新(?:练|做|来|开始)|反复|一次又一次",
        "observe_or_copy": r"观察|模仿|看着.{0,8}学",
        "search_or_discover": r"寻找|线索|发现",
    },
    "repeated_resolution_mechanism": {
        "adjust_method": r"调整|改一个方法|换个方法|换一种办法",
        "peer_help": r"互相帮助|帮忙|合作|共同完成|一起完成",
        "retry_or_practice": r"再试|重新练|反复练|多练",
        "slow_or_find_rhythm": r"慢一点|放慢|找到节奏|找.{0,4}节奏",
        "change_tool": r"换.{0,5}(?:工具|绳|球)|替换材料",
        "ask_for_help": r"请求帮助|请.{0,8}帮",
    },
    "repeated_setting_pattern": {
        "school": r"校园|学校|教室|操场|运动角",
        "home": r"家里|家庭|房间|厨房",
        "park_or_nature": r"公园|森林|花园|山上|河边|海边",
        "fantasy_world": r"云朵|天空|太空|水底|魔法|想象世界|想象岛",
        "community": r"社区|街道|商店|图书馆",
    },
}


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))
    for run in re.findall(r"[\u4e00-\u9fff]+", lowered):
        tokens.update(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return tokens


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a or b else 1.0


def _natural_storyline_complete(text: str) -> bool:
    sentences = [part for part in re.split(r"[。！？!?]+", text) if part.strip()]
    return len(text.strip()) >= 60 and len(sentences) >= 3


def _repeated_pattern_diagnostics(proposals: list[dict], minimum_count: int = 3) -> dict:
    diagnostics = {name: [] for name in DIAGNOSTIC_PATTERNS}
    for signal_name, patterns in DIAGNOSTIC_PATTERNS.items():
        for pattern_name, pattern in patterns.items():
            positions = []
            for position, proposal in enumerate(proposals, 1):
                text = " ".join(str(proposal.get(field, "")) for field in
                                ("entry_point_cn", "storyline", "plot_structure"))
                if re.search(pattern, text):
                    positions.append(position)
            if len(positions) >= minimum_count:
                diagnostics[signal_name].append({"pattern": pattern_name,
                                                 "count": len(positions),
                                                 "proposals": positions})
    return diagnostics


class ProposalValidator:
    def __init__(self, reference: ReferenceDataService):
        self.reference = reference

    def validate(self, payload: dict, expected_count: int, topic: dict,
                 teacher_input: dict | None = None) -> dict:
        issues = []
        proposals = payload.get("proposals") if isinstance(payload, dict) else None
        if not isinstance(proposals, list):
            return {"valid": False, "error_code": "INVALID_SCHEMA",
                    "issues": [{"code": "PROPOSALS_NOT_ARRAY"}], "proposals": [], "metrics": {}}
        if len(proposals) != expected_count:
            issues.append({"code": "PROPOSAL_COUNT", "expected": expected_count, "actual": len(proposals)})
        schema_valid = 0
        storyline_complete = 0
        book_type_valid = 0
        source_summary = Counter()
        enriched = []
        indices = []
        teacher_words = {str(word).strip().lower() for word in (teacher_input or {}).get("added_words", [])}
        for position, proposal in enumerate(proposals, 1):
            if not isinstance(proposal, dict):
                issues.append({"code": "PROPOSAL_NOT_OBJECT", "position": position})
                continue
            missing = [field for field in REQUIRED_PROPOSAL_FIELDS if field not in proposal]
            if missing:
                issues.append({"code": "REQUIRED_FIELDS", "position": position, "missing": missing})
                continue
            type_ok = (isinstance(proposal["proposal_index"], int)
                       and all(isinstance(proposal[field], str) for field in
                               ("title", "entry_point_cn", "storyline", "book_type", "plot_structure",
                                "potential_issues", "creative_highlight"))
                       and all(isinstance(proposal[field], list) and
                               all(isinstance(item, str) and item.strip() for item in proposal[field])
                               for field in ("predicted_core_words", "predicted_core_patterns",
                                             "predicted_extension_words")))
            if not type_ok:
                issues.append({"code": "FIELD_TYPES", "position": position})
                continue
            schema_valid += 1
            indices.append(proposal["proposal_index"])
            if proposal["book_type"] in CANONICAL_BOOK_TYPES:
                book_type_valid += 1
            else:
                issues.append({"code": "INVALID_BOOK_TYPE", "position": position,
                               "value": proposal["book_type"]})
            storyline = proposal["storyline"]
            template_labels = sorted(set(match.group(0).strip("。！？!? \t\n")
                                         for match in STORYLINE_SECTION_LABEL.finditer(storyline)))
            if template_labels:
                issues.append({"code": "TEMPLATE_STYLE_STORYLINE", "position": position,
                               "labels": template_labels})
            if _natural_storyline_complete(storyline):
                storyline_complete += 1
            else:
                issues.append({"code": "INCOMPLETE_STORYLINE", "position": position})
            vocab_checks = []
            textbook = textbook_lookup_forms(topic["textbook_words"])
            for role, field in (("CORE", "predicted_core_words"), ("EXTENSION", "predicted_extension_words")):
                for word in proposal[field]:
                    textbook_hit = word.strip().lower() in textbook
                    scope_hit = bool(self.reference.lookup_textbook_entry(word))
                    teacher_hit = word.strip().lower() in teacher_words
                    status = "TEXTBOOK" if textbook_hit else "TEXTBOOK_SCOPE" if scope_hit \
                        else "TEACHER_ADDED" if teacher_hit else "UNRESOLVED"
                    source_summary[status] += 1
                    vocab_checks.append({"raw_form": word, "predicted_role": role,
                                         "source_status": status,
                                         "manual_review_required": status == "UNRESOLVED"})
            item = dict(proposal)
            item["predicted_vocabulary_validation"] = vocab_checks
            enriched.append(item)
        if sorted(indices) != list(range(1, expected_count + 1)):
            issues.append({"code": "PROPOSAL_INDEX_SEQUENCE", "indices": indices})

        titles = [p.get("title", "").strip().lower() for p in proposals if isinstance(p, dict)]
        duplicate_titles = len(titles) - len(set(titles))
        similar_pairs = []
        for i, left in enumerate(enriched):
            for j, right in enumerate(enriched[i + 1:], i + 1):
                score = _similarity(left["storyline"] + " " + left["plot_structure"],
                                    right["storyline"] + " " + right["plot_structure"])
                if score >= 0.82:
                    similar_pairs.append({"left": i + 1, "right": j + 1, "similarity": round(score, 3)})
        if duplicate_titles:
            issues.append({"code": "DUPLICATED_TITLES", "count": duplicate_titles})
        if similar_pairs:
            issues.append({"code": "LOW_DIVERSITY", "pairs": similar_pairs})
        repeated_patterns = _repeated_pattern_diagnostics(enriched)
        for signal_name, matches in repeated_patterns.items():
            if matches:
                issues.append({"code": signal_name.upper(), "severity": "INFO", "matches": matches})
        count = len(proposals) or 1
        metrics = {
            "proposal_count": len(proposals),
            "schema_valid_rate": schema_valid / count,
            "duplicated_title_rate": duplicate_titles / count,
            "storyline_completeness": storyline_complete / count,
            "book_type_validity": book_type_valid / count,
            "textbook_fact_consistency": all(p.get("book_type") in CANONICAL_BOOK_TYPES for p in proposals if isinstance(p, dict)),
            "predicted_vocab_source_status": dict(source_summary),
            "diversity_signals": {"similar_pairs": similar_pairs,
                                  "unique_book_types": len({p.get("book_type") for p in proposals if isinstance(p, dict)}),
                                  "unique_titles": len(set(titles)),
                                  **repeated_patterns},
        }
        blocking_codes = {"PROPOSAL_COUNT", "PROPOSAL_NOT_OBJECT", "REQUIRED_FIELDS", "FIELD_TYPES",
                          "INVALID_BOOK_TYPE", "INCOMPLETE_STORYLINE", "TEMPLATE_STYLE_STORYLINE",
                          "PROPOSAL_INDEX_SEQUENCE",
                          "DUPLICATED_TITLES", "LOW_DIVERSITY"}
        valid = not any(issue["code"] in blocking_codes for issue in issues)
        return {"valid": valid, "error_code": None if valid else "VALIDATION_FAILED",
                "issues": issues, "proposals": enriched, "metrics": metrics}
