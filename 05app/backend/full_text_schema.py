"""Structured schemas for Full Text candidates and rewrite previews."""

from __future__ import annotations

import json
import re

PAGE_SCHEMA = {
    "type": "object",
    "required": ["page_number", "text"],
    "properties": {
        "page_number": {"type": "integer"},
        "text": {"type": "string"},
    },
}

FULL_TEXT_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array", "minItems": 2, "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["candidate_index", "title", "page_count", "pages",
                             "requires_fact_verification"],
                "properties": {
                    "candidate_index": {"type": "integer"},
                    "title": {"type": "string"},
                    "page_count": {"type": "integer"},
                    "pages": {"type": "array", "items": PAGE_SCHEMA},
                    "requires_fact_verification": {"type": "boolean"},
                },
            },
        },
    },
}

FULL_REWRITE_OUTPUT_SCHEMA = {
    "type": "object", "required": ["title", "pages", "requires_fact_verification"],
    "properties": {
        "title": {"type": "string"},
        "pages": {"type": "array", "items": PAGE_SCHEMA},
        "requires_fact_verification": {"type": "boolean"},
    },
}

PAGE_REWRITE_OUTPUT_SCHEMA = {
    "type": "object", "required": ["page_number", "text", "requires_fact_verification"],
    "properties": {
        "page_number": {"type": "integer"},
        "text": {"type": "string"},
        "requires_fact_verification": {"type": "boolean"},
    },
}


def parse_json_object(text: str) -> tuple[dict | None, str | None]:
    value, diagnostic = parse_json_object_diagnostic(text)
    return value, diagnostic["code"] if diagnostic else None


def parse_json_object_diagnostic(text: str) -> tuple[dict | None, dict | None]:
    if not text or not text.strip():
        return None, {"code": "EMPTY_OUTPUT", "message": "Provider content is empty",
                      "failed_field_path": "$"}
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned,
                          flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, {"code": "INVALID_JSON", "message": exc.msg,
                      "failed_field_path": f"$[line={exc.lineno},column={exc.colno}]"}
    if not isinstance(value, dict):
        return None, {"code": "ROOT_NOT_OBJECT",
                      "message": "Top-level JSON value must be an object",
                      "failed_field_path": "$"}
    return value, None
