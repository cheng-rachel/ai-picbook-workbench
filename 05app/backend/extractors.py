"""Deterministic extraction from the human-maintained 01docs sources.

Textbook basis: Cambridge Power Up Second Edition, Level 2 (9 units).
Sources are never rewritten here; fuzzy source rows (e.g. lists ending with
"等") are extracted conservatively and reported as warnings, never expanded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re

from .docx_reader import read_docx

SOURCE_FILES = {
    "design": "01绘本编写理念.docx",
    "levels": "02分级标准.docx",
    "language": "03语言项目收录标准.docx",
    "topics": "04Level2教材依据.docx",
}


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def _source(path: Path, key: str) -> dict:
    return {
        "source_document_id": key,
        "source_name": path.stem,
        "source_path": str(path.relative_to(path.parent.parent)),
        "source_type": "docx",
        "source_hash": sha256(path.read_bytes()).hexdigest(),
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    }


# Latin word/phrase lead of a source fragment; keeps slashes ("leaf/leaves"),
# hyphens ("T-shirt") and apostrophes ("o'clock") but stops at Chinese text.
_ENGLISH_LEAD = re.compile(r"[A-Za-z][A-Za-z'’\-/ ]*")
_NON_EXHAUSTIVE_MARKS = ("等", "以及", "such as", "etc")


def _parse_word_group(cell: str) -> tuple[str, list[str], list[str]]:
    """Parse one textbook word cell: "Group label: w1, w2, ... [等...]".

    Returns (group_label, entries, warnings). Only explicitly listed items are
    extracted; trailing "等…" style descriptions become warnings, not words.
    """
    warnings: list[str] = []
    label, _, body = cell.partition(":")
    if not body:
        label, _, body = cell.partition("：")
    label = label.strip()
    body = body.strip()
    if "such as" in body:
        warnings.append(f"non-exhaustive source list (such as): {cell}")
        body = body.split("such as", 1)[1]
    entries: list[str] = []
    for fragment in re.split(r"[,，、]", body):
        fragment = fragment.strip()
        if not fragment:
            continue
        match = _ENGLISH_LEAD.match(fragment)
        if not match:
            # Pure descriptive text (e.g. "以及餐具词汇") is a warning only.
            warnings.append(f"non-english fragment kept as note: {fragment}")
            continue
        entry = match.group(0).strip().strip("/-")
        remainder = fragment[match.end():].strip()
        if remainder and any(mark in remainder for mark in _NON_EXHAUSTIVE_MARKS):
            warnings.append(f"non-exhaustive source list: {fragment}")
        elif remainder:
            warnings.append(f"trailing source note ignored: {fragment}")
        if entry:
            entries.append(entry)
    return label, entries, warnings


def extract_topics(path: Path) -> dict:
    doc = read_docx(path)
    if len(doc.tables) < 2:
        raise ValueError("Power Up 2 textbook source needs the unit table and the word table")
    topics, words, structures = [], [], []
    warnings: list[dict] = []
    for row in doc.tables[0][1:]:
        if len(row) < 7 or not re.fullmatch(r"Unit\s+\d+", row[0].strip()):
            continue
        number = int(row[0].split()[-1])
        topic_id = f"L2-T{number:02d}"
        topics.append({
            "topic_id": topic_id,
            "level_id": 2,
            "semester": "Power Up 2",
            "unit_number": number,
            "topic_number": number,
            "unit_title": row[1].strip(),
            "theme": row[3].strip(),
            "essential_question": row[2].strip(),
            "grammar_text": row[4].strip(),
            "cross_curricular_text": row[5].strip(),
            "literature_text": row[6].strip(),
            "source_document_id": "topics",
            "active": True,
        })
        for seq, entry in enumerate(
                (part.strip() for part in row[4].split(";") if part.strip()), 1):
            structures.append({"topic_id": topic_id, "raw_structure": entry,
                               "normalized_pattern": None, "sequence_no": seq,
                               "source_document_id": "topics"})

    by_unit = {topic["unit_number"]: topic for topic in topics}
    for row in doc.tables[1][1:]:
        if len(row) < 4 or not re.fullmatch(r"Unit\s+\d+", row[0].strip()):
            continue
        number = int(row[0].split()[-1])
        topic = by_unit.get(number)
        if topic is None:
            continue
        sequence = 0
        for cell in (row[2], row[3]):
            group, entries, cell_warnings = _parse_word_group(cell)
            for message in cell_warnings:
                warnings.append({"code": "TEXTBOOK_WORDS_PARTIAL",
                                 "topic": topic["topic_id"], "group": group,
                                 "message": message})
            for entry in entries:
                sequence += 1
                words.append({"topic_id": topic["topic_id"], "raw_entry": entry,
                              "normalized_entry": normalize(entry),
                              "entry_type": "phrase" if " " in entry else "word",
                              "sequence_no": sequence,
                              "source_document_id": "topics"})
    # Power Up 2 source has no extra example-sentence sheet; keep the container
    # so downstream schema and prompt assembly stay unchanged.
    return {"topics": topics, "textbook_words": words,
            "textbook_structures": structures, "textbook_examples": [],
            "extraction_warnings": warnings}


def _range_value(text: str) -> str:
    match = re.search(r"(\d+)\s*[-—–]\s*(\d+)", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    match = re.search(r"[≥>=至少]+\s*(\d+)", text)
    if match:
        return f"{match.group(1)}+"
    raise ValueError(f"Expected numeric range in source text: {text}")


def _level_table_rows(table: list[list[str]]) -> dict[str, str]:
    """Collapse the Level table to {dimension: level-2 cell}, skipping repeated headers."""
    rows = {}
    for row in table:
        if len(row) < 3 or row[0].strip() in ("", "维度"):
            continue
        rows[row[0].strip()] = row[2].strip()
    return rows


def extract_level_rules(level_path: Path, language_path: Path) -> dict:
    level_doc, language_doc = read_docx(level_path), read_docx(language_path)
    descriptions = _level_table_rows(level_doc.tables[0])
    vocab_row = next(row for row in language_doc.tables[2] if row and row[0].strip() == "Level 2")
    pattern_row = next(row for row in language_doc.tables[4] if row and row[0].strip() == "Level 2")

    source_values = {
        "level_book_word_count": _range_value(descriptions["每册阅读量"]),
        "language_book_word_count": _range_value(vocab_row[2]),
        "core_word_frequency": _range_value(vocab_row[6]),
        "cross_book_recurrence": _range_value(vocab_row[7]),
        "pattern_repeat": _range_value(pattern_row[2]),
    }
    rules = [
        ("book_word_count", descriptions["每册阅读量"], {"min": 120, "max": 200},
         "range", "target", "levels", "每册阅读量"),
        ("page_count_allowed", "Product Decision", [8, 12], "json", "hard",
         "product", "01_product_workflow Stage 15.1"),
        ("sentences_per_page", "Product Decision（01docs 未另行规定）", {"min": 2, "max": 3},
         "range", "target", "product", "01_product_workflow Stage 15.3"),
        ("sentence_max_words", "Product Decision（01docs 未另行规定）", 10,
         "int", "target", "product", "01_product_workflow Stage 15.4"),
        ("core_pattern_count", pattern_row[1], {"min": 1, "max": 2},
         "range", "target", "language", "每册语句数据"),
        ("core_pattern_repeat", pattern_row[2], {"min": 3, "max": 5},
         "range", "target", "language", "每册语句数据"),
        ("core_word_frequency", vocab_row[6], {"min": 3, "max": 5},
         "range", "target", "language", "分级词汇与篇幅标准"),
        ("review_words_per_book", "复现池≥5时建议5–6个（Product Decision）", {"min": 5, "max": 6},
         "range", "target", "product", "01_product_workflow Stage 14.2"),
        ("cross_book_recurrence", vocab_row[7], {"min": 3, "max": 5},
         "range", "target", "language", "分级词汇与篇幅标准"),
    ]
    stage = descriptions["核心阅读目标"].split("：", 1)[0].strip()
    return {"level": {"level_id": 2, "level_name": "Level 2",
                      "stage_positioning": stage, "active_in_demo": True},
            "level_rules": [{"level_rule_id": f"L2-{key}", "level_id": 2,
                             "rule_key": key, "raw_value": raw, "effective_value": effective,
                             "value_type": typ, "rule_strength": strength,
                             "source_document_id": source, "source_section": section,
                             "note": None} for key, raw, effective, typ, strength, source, section in rules],
            "descriptions": descriptions, "source_values": source_values}


def extract_all(docs_dir: Path) -> dict:
    paths = {key: docs_dir / filename for key, filename in SOURCE_FILES.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required sources: " + ", ".join(missing))
    result = {"source_documents": [_source(path, key) for key, path in paths.items()]}
    result.update(extract_topics(paths["topics"]))
    result.update(extract_level_rules(paths["levels"], paths["language"]))
    result["book_types"] = [
        {"code": "TEXTBOOK_SYNC", "display_name_zh": "教材衔接", "core_positioning": "换情境，练所学"},
        {"code": "THEME_EXTENSION", "display_name_zh": "主题拓展", "core_positioning": "从主题出发，进一步思考"},
        {"code": "CROSS_CURRICULAR", "display_name_zh": "跨学科提升", "core_positioning": "借主题认识更大的世界"},
    ]
    result["product_overrides"] = [
        {"rule_key": "level2.book_word_count", "effective_value": {"min": 120, "max": 200}, "reason": "Product Decision"},
        {"rule_key": "vocabulary_detection_v1", "effective_value": "lemma_normalization + manual_review_warning", "reason": "Product Decision"},
        # 03语言项目收录标准「分级词汇与篇幅标准」: Level 2 规划册数 63 册 = 9 单元 × 7 册。
        # 三类（教材衔接/主题拓展/跨学科提升）在 7 本中的数量分配 docx 未规定：HUMAN DECISION REQUIRED，
        # 三类分配已由人工确认（2026-08-19）：教材衔接 2 / 主题拓展 3 / 跨学科提升 2。
        {"rule_key": "topic_final_quota", "effective_value": {"total": 7, "per_book_type": {"TEXTBOOK_SYNC": 2, "THEME_EXTENSION": 3, "CROSS_CURRICULAR": 2}}, "reason": "03语言项目收录标准: 63册/9单元=7册；三类分配 2026-08-19 人工确认为 2/3/2"},
        {"rule_key": "book_number.allocation", "effective_value": {"scope": "LEVEL", "required_current_finals": 63, "allocate_after_all_finalized": True, "teacher_reordering_allowed": True}, "reason": "Power Up 2 has 9 units × 7 finals = 63"},
        {"rule_key": "export.extension_words", "effective_value": {"merge_theme_and_cultural": True, "column_name": "Words to know"}, "reason": "2026-08-16 Product Decision"},
        {"rule_key": "vocabulary_source_scope", "effective_value": "power_up_2_textbook_words_only", "reason": "01docs no longer includes a separate curriculum vocabulary source"},
    ]
    result["source_conflicts"] = [
        {"conflict_id": "level2-core-word-frequency", "rule_key": "level2.core_word_frequency",
         "variants": [{"source_document_id": "language", "raw_value": result["source_values"]["core_word_frequency"] + "次（分级词汇与篇幅标准）"},
                      {"source_document_id": "language", "raw_value": "大于等于3（核心词复现规则正文）"}],
         "resolution_status": "resolved", "resolution_note": "单篇核心词复现按3-5次为建议目标，不是Final硬约束"},
        {"conflict_id": "level2-recurrence", "rule_key": "level2.cross_book_recurrence",
         "variants": [{"source_document_id": "language", "raw_value": "同级跨册复现" + result["source_values"]["cross_book_recurrence"] + "册"},
                      {"source_document_id": "product", "raw_value": "跨书复现3-5次为建议目标"}],
         "resolution_status": "resolved", "resolution_note": "3-5次为建议目标，最低≥3册；均不是Final硬约束"},
    ]
    return result
