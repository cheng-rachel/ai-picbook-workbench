#!/usr/bin/env python3
"""Rebuild human-readable intermediates and static SQLite reference data."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DATABASE_PATH, DOCS_DIR, RAG_INDEX_PATH, RAG_PROCESSED_DIR, STRUCTURED_DIR  # noqa: E402
from backend.database import build_database  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.rag_builder import build_rag  # noqa: E402
from backend.validation import validate_sources  # noqa: E402


def write_json(name: str, value) -> None:
    (STRUCTURED_DIR / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    data = extract_all(DOCS_DIR)
    report = validate_sources(data)
    write_json("source_documents.json", data["source_documents"])
    write_json("level_rules.json", {"level": data["level"], "rules": data["level_rules"], "descriptions": data["descriptions"]})
    write_json("book_types.json", data["book_types"])
    write_json("level2_topics.json", data["topics"])
    write_json("textbook_words.json", data["textbook_words"])
    write_json("textbook_structures.json", data["textbook_structures"])
    write_json("textbook_language_examples.json", data["textbook_examples"])
    write_json("source_conflicts.json", data["source_conflicts"])
    write_json("validation_report.json", report)
    if report["failures"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    build_database(DATABASE_PATH, data)
    rag_manifest = build_rag(DOCS_DIR, RAG_PROCESSED_DIR, RAG_INDEX_PATH)
    print(f"Structured data ready: {STRUCTURED_DIR}")
    print(f"Database ready: {DATABASE_PATH}")
    print(f"Validation: {report['status']} {report['metrics']}")
    print(f"Warnings: {len(report['warnings'])}; Failures: {len(report['failures'])}")
    print(f"RAG ready: {RAG_INDEX_PATH} ({rag_manifest['chunk_count']} chunks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
