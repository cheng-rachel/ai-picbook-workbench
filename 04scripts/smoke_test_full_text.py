#!/usr/bin/env python3
"""Optional real-provider Full-text smoke test; safely skipped without credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import ModelSettings  # noqa: E402
from backend.full_text_workflow import FullTextWorkflow  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Full-text Candidates for an existing READY Plan."
    )
    parser.add_argument("plan_id", help="Existing READY Pre-generation Plan ID")
    parser.add_argument(
        "--candidate-count", type=int, choices=(2, 3), default=3,
        help="Number of candidates to generate (default: 3)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = ModelSettings.from_environment()
    if not settings.api_key or not settings.api_url or settings.full_text_model == "default":
        print(json.dumps({
            "ok": True,
            "status": "SKIP",
            "message": "Configure MODEL_API_KEY, MODEL_API_URL and FULL_TEXT_MODEL for a real smoke test.",
            "plan_id": args.plan_id,
            "candidate_count": args.candidate_count,
            "candidate_ids": [],
        }, ensure_ascii=False, indent=2))
        return 0

    result = FullTextWorkflow(settings=settings).generate_full_text_candidates(
        plan_id=args.plan_id,
        candidate_count=args.candidate_count,
    )
    output = {
        "ok": result.get("ok", False),
        "error_code": result.get("error_code"),
        "message": result.get("message"),
        "attempts": result.get("attempts"),
        "model": settings.full_text_model,
        "plan_id": args.plan_id,
        "project_id": result.get("project_id"),
        "full_text_candidate_batch_id": result.get("full_text_candidate_batch_id"),
        "candidate_count": result.get("candidate_count", 0),
        "candidate_ids": [item["candidate_id"] for item in result.get("candidates", [])],
        "candidates": result.get("candidates", []),
        "context_status": result.get("context_status"),
        "schema_failure_attempts": result.get("schema_failure_attempts", []),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
