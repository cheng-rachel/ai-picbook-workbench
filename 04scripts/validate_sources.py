#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))
from backend.config import DOCS_DIR  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.validation import validate_sources  # noqa: E402

report = validate_sources(extract_all(DOCS_DIR))
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(1 if report["failures"] else 0)

