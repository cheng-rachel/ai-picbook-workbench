"""Proposal structured-output schema and deterministic parsing."""

from __future__ import annotations

import json
import re

CANONICAL_BOOK_TYPES = {"TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR"}
REQUIRED_PROPOSAL_FIELDS = (
    "proposal_index", "title", "entry_point_cn", "storyline", "predicted_core_words",
    "predicted_core_patterns", "predicted_extension_words", "book_type", "plot_structure",
    "potential_issues", "creative_highlight",
)

PROPOSAL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["proposals"],
    "properties": {
        "proposals": {"type": "array", "minItems": 6, "maxItems": 10,
                      "items": {"type": "object", "required": list(REQUIRED_PROPOSAL_FIELDS),
                                "properties": {
                                    "proposal_index": {"type": "integer"},
                                    "title": {"type": "string"},
                                    "entry_point_cn": {"type": "string"},
                                    "storyline": {"type": "string"},
                                    "predicted_core_words": {"type": "array", "items": {"type": "string"}},
                                    "predicted_core_patterns": {"type": "array", "items": {"type": "string"}},
                                    "predicted_extension_words": {"type": "array", "items": {"type": "string"}},
                                    "book_type": {"type": "string", "enum": sorted(CANONICAL_BOOK_TYPES)},
                                    "plot_structure": {"type": "string"},
                                    "potential_issues": {"type": "string"},
                                    "creative_highlight": {"type": "string"},
                                }}}
    },
}


# Suggestions only: the result still passes through the normal Pre-generation
# Plan where the teacher reviews, edits, and confirms before anything is READY.
LANGUAGE_RECOMMENDATION_SCHEMA = {
    "type": "object",
    "required": ["predicted_core_words", "predicted_extension_words",
                 "predicted_core_patterns"],
    "properties": {
        "predicted_core_words": {"type": "array", "minItems": 1, "maxItems": 5,
                                 "items": {"type": "string"}},
        "predicted_extension_words": {"type": "array", "maxItems": 4,
                                      "items": {"type": "string"}},
        "predicted_core_patterns": {"type": "array", "minItems": 1, "maxItems": 2,
                                    "items": {"type": "string"}},
    },
}


def parse_model_json(text: str) -> tuple[dict | None, str | None]:
    if not text or not text.strip():
        return None, "EMPTY_OUTPUT"
    cleaned = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, "INVALID_SCHEMA"
    if isinstance(value, list):
        value = {"proposals": value}
    return (value, None) if isinstance(value, dict) else (None, "INVALID_SCHEMA")
