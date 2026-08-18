"""Build rule-aware teaching guidance chunks and a local lexical index.

Sources are the Power Up 2 edition of the three principle documents. The
authoritative unit data (04Level2教材依据.docx) never enters RAG: those facts
live in the structured database only.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import log
from pathlib import Path
import re

from .docx_reader import read_docx

RAG_SOURCES = {
    "design": "01绘本编写理念.docx",
    "levels": "02分级标准.docx",
    "language": "03语言项目收录标准.docx",
}


def file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_]+", lowered)
    chinese_runs = re.findall(r"[\u4e00-\u9fff]+", lowered)
    chinese = [run[i:i + 2] for run in chinese_runs for i in range(max(1, len(run) - 1))]
    return latin + chinese


def _chunk(source: str, section: str, heading: str, text: str, rule_type: str,
           level_scope: str = "ALL", book_type_scope: str = "ALL",
           task_scope: list[str] | None = None, priority: str = "NORMAL",
           non_authoritative: bool = False) -> dict:
    seed = f"{source}|{section}|{heading}|{text}"
    return {
        "chunk_id": "rag-" + sha256(seed.encode("utf-8")).hexdigest()[:16],
        "source_document": source,
        "source_section": section,
        "source_heading": heading,
        "text": text,
        "rule_type": rule_type,
        "level_scope": level_scope,
        "book_type_scope": book_type_scope,
        "topic_scope": "ALL",
        "task_scope": task_scope or ["ALL"],
        "verification_status": "VERIFIED",
        "priority": priority,
        "non_authoritative_for_runtime_numeric_rules": non_authoritative,
    }


def _sections(paragraphs: list[str], heading_pattern: str) -> dict[str, str]:
    """Group paragraphs into {heading: joined body} using a heading regex."""
    matcher = re.compile(heading_pattern)
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for paragraph in paragraphs:
        if matcher.match(paragraph):
            current = paragraph
            sections[current] = []
        elif current is not None:
            sections[current].append(paragraph)
    return {heading: "\n".join(body).strip() for heading, body in sections.items() if body}


def _level2_rows(table: list[list[str]]) -> dict[str, str]:
    rows = {}
    for row in table:
        if len(row) < 3 or row[0].strip() in ("", "维度"):
            continue
        rows[row[0].strip()] = row[2].strip()
    return rows


def extract_rag_chunks(docs_dir: Path) -> tuple[list[dict], dict[str, str]]:
    paths = {key: docs_dir / name for key, name in RAG_SOURCES.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing RAG source: " + ", ".join(missing))
    hashes = {path.name: file_hash(path) for path in paths.values()}
    chunks: list[dict] = []

    # ---- 01 绘本编写理念: principle sections -------------------------------
    design = read_docx(paths["design"])
    design_sections = _sections(design.paragraphs, r"^(一、设计理念|（[一二三四五]）)")
    design_pairs = {
        "一、设计理念": ("DESIGN_PHILOSOPHY", "NORMAL"),
        "（一）教材衔接": ("DESIGN_PHILOSOPHY", "NORMAL"),
        "（二）分级递进": ("LEVEL_READING_GOAL", "NORMAL"),
        "（三）核心语言复现": ("RECURRENCE_PRINCIPLE", "NORMAL"),
        "（四）语言真实、自然、可理解": ("PRAGMATIC_NATURALNESS", "HIGH"),
        "（五）内容与事实准确": ("FACTUAL_ACCURACY", "HIGH"),
    }
    for heading, (rule_type, priority) in design_pairs.items():
        body = design_sections.get(heading)
        if body:
            chunks.append(_chunk(paths["design"].name, "编写理念", heading, body, rule_type,
                                 task_scope=["PROPOSAL", "FULL_TEXT", "REWRITE"],
                                 priority=priority))

    # ---- 02 分级标准: Level 2 explanatory dimensions -----------------------
    levels = read_docx(paths["levels"])
    for paragraph in levels.paragraphs:
        if "Power Up 2" in paragraph:
            chunks.append(_chunk(paths["levels"].name, "总述", "教材依据",
                                 paragraph, "DESIGN_PHILOSOPHY",
                                 level_scope="LEVEL_2",
                                 task_scope=["PROPOSAL", "FULL_TEXT"]))
            break
    level_rows = _level2_rows(levels.tables[0])
    level_mapping = {
        "核心阅读目标": ("LEVEL_READING_GOAL", False),
        "主题梯度": ("TOPIC_GRADIENT", False),
        "文化意识": ("CROSS_CURRICULAR", False),
        "每册阅读量": ("LEVEL_READING_GOAL", True),
        "句式难度": ("LEVEL_READING_GOAL", False),
        "篇章类型": ("PLOT_GUIDANCE", False),
        "情节特征": ("PLOT_GUIDANCE", False),
        "写作手法": ("WRITING_METHOD", False),
    }
    for heading, (rule_type, non_authoritative) in level_mapping.items():
        if heading in level_rows:
            chunks.append(_chunk(paths["levels"].name, "Level 2", heading,
                                 f"Level 2 {heading}：{level_rows[heading]}", rule_type,
                                 level_scope="LEVEL_2",
                                 task_scope=["PROPOSAL", "FULL_TEXT", "REWRITE"],
                                 non_authoritative=non_authoritative))

    # ---- 03 语言项目收录标准 ------------------------------------------------
    language = read_docx(paths["language"])
    paragraphs = language.paragraphs

    # Book-type principles: intro paragraphs plus the worked example table.
    type_paragraphs = [
        ("教材衔接：", "TEXTBOOK_SYNC"),
        ("主题拓展：", "THEME_EXTENSION"),
        ("跨学科提升：", "CROSS_CURRICULAR"),
    ]
    for prefix, scope in type_paragraphs:
        matching = [p for p in paragraphs if p.startswith(prefix)]
        if matching:
            chunks.append(_chunk(paths["language"].name, "主题选择原则", prefix.rstrip("："),
                                 matching[0], "BOOK_TYPE_GUIDANCE", level_scope="LEVEL_2",
                                 book_type_scope=scope,
                                 task_scope=["PROPOSAL", "FULL_TEXT", "REWRITE"]))
    diversity = [p for p in paragraphs if p.startswith("同一单元设计多个故事方案")]
    if diversity:
        chunks.append(_chunk(paths["language"].name, "主题选择原则", "故事方案多样性",
                             diversity[0], "PLOT_GUIDANCE", level_scope="ALL",
                             task_scope=["PROPOSAL"], priority="HIGH"))
    headers = language.tables[0][0]
    code_by_label = {"教材衔接": "TEXTBOOK_SYNC", "主题拓展": "THEME_EXTENSION",
                     "跨学科提升": "CROSS_CURRICULAR"}
    for row in language.tables[0][1:]:
        if len(row) < 5 or row[0].strip() not in code_by_label:
            continue
        text = "；".join(f"{header}：{cell}" for header, cell in zip(headers, row) if cell)
        chunks.append(_chunk(paths["language"].name, "主题发散示例", row[0].strip(), text,
                             "BOOK_TYPE_GUIDANCE", level_scope="LEVEL_2",
                             book_type_scope=code_by_label[row[0].strip()],
                             task_scope=["PROPOSAL"]))

    # Vocabulary principles.
    vocab_rules = [
        ("· 核心词（CORE）", "词汇分类与来源", "VOCABULARY_PRINCIPLE",
         ["PROPOSAL", "FULL_TEXT", "VOCAB_CLASSIFICATION"], "NORMAL"),
        ("· 拓展词（EXTENSION）", "词汇分类与来源", "VOCABULARY_PRINCIPLE",
         ["PROPOSAL", "FULL_TEXT", "VOCAB_CLASSIFICATION"], "NORMAL"),
        ("· 复现词（REVIEW）", "词汇分类与来源", "RECURRENCE_PRINCIPLE",
         ["FULL_TEXT", "REVIEW_RECOMMENDATION"], "NORMAL"),
        ("故事创作过程中允许出现少量", "非目标词汇的处理", "VOCABULARY_PRINCIPLE",
         ["FULL_TEXT", "VOCAB_CLASSIFICATION"], "HIGH"),
        ("（1）一词多义", "词汇收录补充说明", "VOCABULARY_PRINCIPLE", ["VOCAB_CLASSIFICATION"], "NORMAL"),
        ("（2）短语动词", "词汇收录补充说明", "VOCABULARY_PRINCIPLE", ["VOCAB_CLASSIFICATION"], "NORMAL"),
        ("（3）合成词", "词汇收录补充说明", "VOCABULARY_PRINCIPLE", ["VOCAB_CLASSIFICATION"], "NORMAL"),
        ("（4）派生词", "词汇收录补充说明", "VOCABULARY_PRINCIPLE", ["VOCAB_CLASSIFICATION"], "NORMAL"),
        ("（5）词性转换", "词汇收录补充说明", "VOCABULARY_PRINCIPLE", ["VOCAB_CLASSIFICATION"], "NORMAL"),
    ]
    for prefix, section, rule_type, tasks, priority in vocab_rules:
        matching = [p for p in paragraphs if p.startswith(prefix)]
        if matching:
            chunks.append(_chunk(paths["language"].name, section, prefix.strip("·（） "),
                                 matching[0], rule_type, level_scope="ALL",
                                 task_scope=tasks, priority=priority))

    # Word-difficulty judgement: heading followed by explanation and example.
    difficulty_sections = _sections(paragraphs, r"^(词汇难度判断|核心词复现规则|词汇复现规则|词汇收录补充说明)$")
    difficulty_pairs = {
        "词汇难度判断": ("PRAGMATIC_NATURALNESS", "HIGH",
                         ["FULL_TEXT", "REWRITE", "VOCAB_CLASSIFICATION"], False),
        "核心词复现规则": ("RECURRENCE_PRINCIPLE", "NORMAL",
                           ["FULL_TEXT", "REVIEW_RECOMMENDATION"], True),
        "词汇复现规则": ("RECURRENCE_PRINCIPLE", "NORMAL",
                         ["FULL_TEXT", "REVIEW_RECOMMENDATION"], True),
    }
    for heading, (rule_type, priority, tasks, non_authoritative) in difficulty_pairs.items():
        body = difficulty_sections.get(heading)
        if body:
            chunks.append(_chunk(paths["language"].name, "词汇收录标准", heading, body,
                                 rule_type, level_scope="ALL", task_scope=tasks,
                                 priority=priority, non_authoritative=non_authoritative))

    # Sentence-project principles: core pattern / supporting / discourse.
    pattern_rules = [
        ("核心句型（CORE PATTERN）", "PATTERN_PRINCIPLE",
         ["PROPOSAL", "FULL_TEXT", "REWRITE"], "HIGH"),
        ("配套表达（SUPPORTING EXPRESSION）", "PATTERN_PRINCIPLE", ["FULL_TEXT", "REWRITE"], "NORMAL"),
        ("语篇组织表达（DISCOURSE EXPRESSION）", "PATTERN_PRINCIPLE", ["FULL_TEXT", "REWRITE"], "NORMAL"),
        ("语句项目的组织围绕一个原则", "PATTERN_PRINCIPLE", ["FULL_TEXT", "REWRITE"], "HIGH"),
        ("核心句型按语言结构与语用功能归类", "PATTERN_PRINCIPLE", ["FULL_TEXT", "REWRITE"], "NORMAL"),
    ]
    for prefix, rule_type, tasks, priority in pattern_rules:
        matching = [p for p in paragraphs if p.startswith(prefix)]
        if matching:
            chunks.append(_chunk(paths["language"].name, "语句收录标准", prefix.split("（")[0],
                                 matching[0], rule_type, level_scope="ALL",
                                 task_scope=tasks, priority=priority))

    # Numeric explanatory rows stay retrievable but never authoritative.
    vocab_row = next(row for row in language.tables[2] if row and row[0].strip() == "Level 2")
    pattern_row = next(row for row in language.tables[4] if row and row[0].strip() == "Level 2")
    chunks.append(_chunk(paths["language"].name, "分级词汇与篇幅标准", "Level 2词汇原始规则",
                         "；".join(f"{h}：{v}" for h, v in zip(language.tables[2][0], vocab_row)),
                         "VOCABULARY_PRINCIPLE", level_scope="LEVEL_2",
                         task_scope=["FULL_TEXT", "VOCAB_CLASSIFICATION", "REVIEW_RECOMMENDATION"],
                         non_authoritative=True))
    chunks.append(_chunk(paths["language"].name, "每册语句数据", "Level 2句型原始规则",
                         "；".join(f"{h}：{v}" for h, v in zip(language.tables[4][0], pattern_row)),
                         "PATTERN_PRINCIPLE", level_scope="LEVEL_2",
                         task_scope=["FULL_TEXT", "REWRITE"], non_authoritative=True))
    for table_index, rule_type, section in ((1, "VOCABULARY_PRINCIPLE", "词汇来源占比"),
                                            (3, "PATTERN_PRINCIPLE", "语句来源占比")):
        table = language.tables[table_index]
        text = "；".join("，".join(f"{h}：{cell}" for h, cell in zip(table[0], row) if cell)
                          for row in table[1:] if any(row))
        chunks.append(_chunk(paths["language"].name, section, section, text, rule_type,
                             level_scope="ALL", task_scope=["PROPOSAL", "FULL_TEXT"],
                             non_authoritative=True))

    for chunk in chunks:
        chunk["source_hash"] = hashes[chunk["source_document"]]
    return chunks, hashes


def build_rag(docs_dir: Path, processed_dir: Path, index_path: Path) -> dict:
    chunks, source_hashes = extract_rag_chunks(docs_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path = processed_dir / "teaching_guidance.jsonl"
    chunks_path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    doc_freq = Counter(term for chunk in chunks for term in set(tokenize(chunk["text"])))
    total = len(chunks)
    index_docs = []
    for chunk in chunks:
        term_counts = Counter(tokenize(chunk["text"] + " " + chunk["source_heading"]))
        weights = {term: count * (log((total + 1) / (doc_freq.get(term, 0) + 1)) + 1)
                   for term, count in term_counts.items()}
        index_docs.append({"chunk_id": chunk["chunk_id"], "weights": weights})
    built_at = datetime.now(timezone.utc).isoformat()
    manifest = {"schema_version": 1, "built_at": built_at, "source_hashes": source_hashes,
                "chunk_count": total, "processed_file": chunks_path.name}
    (processed_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path.write_text(json.dumps({"schema_version": 1, "built_at": built_at,
                                      "source_hashes": source_hashes, "documents": index_docs},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def build_rag_safely(docs_dir: Path, processed_dir: Path, index_path: Path) -> dict:
    try:
        manifest = build_rag(docs_dir, processed_dir, index_path)
        return {"state": "READY", "available": True, "message": "RAG build completed",
                "source_files": [], "manifest": manifest}
    except Exception as exc:
        source_files = [name for name in RAG_SOURCES.values() if name in str(exc)]
        return {"state": "BUILD_FAILED", "available": False, "message": str(exc),
                "source_files": source_files, "manifest": None}
