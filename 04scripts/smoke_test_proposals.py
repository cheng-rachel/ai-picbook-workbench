#!/usr/bin/env python3
"""Optional real-provider smoke test; skipped when backend credentials are absent."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import ModelSettings  # noqa: E402
from backend.proposal_workflow import ProposalWorkflow  # noqa: E402


def main() -> int:
    settings = ModelSettings.from_environment()
    if not settings.api_key or not settings.api_url or settings.proposal_model == "default":
        print("SKIP: configure MODEL_API_KEY, MODEL_API_URL and PROPOSAL_MODEL for a real smoke test")
        return 0
    result = ProposalWorkflow(settings=settings).generate_proposals(
        topic_id=8, count=8,
        teacher_input={"creative_instruction": "故事要适合二年级学生，由行动体现坚持，不要说教。"})
    summary = {key: result.get(key) for key in
               ("ok", "error_code", "message", "attempts", "project_id", "proposal_batch_id")}
    summary["proposal_count"] = len(result.get("proposals", []))
    summary["metrics"] = result.get("validation", {}).get("metrics")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
