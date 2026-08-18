#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DOCS_DIR, RAG_INDEX_PATH, RAG_PROCESSED_DIR  # noqa: E402
from backend.rag_builder import build_rag_safely  # noqa: E402


def main() -> int:
    result = build_rag_safely(DOCS_DIR, RAG_PROCESSED_DIR, RAG_INDEX_PATH)
    if result["state"] != "READY":
        print(json.dumps(result, ensure_ascii=False))
        return 1
    manifest = result["manifest"]
    print(f"RAG processed ready: {RAG_PROCESSED_DIR}")
    print(f"RAG index ready: {RAG_INDEX_PATH}")
    print(f"RAG chunks: {manifest['chunk_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
