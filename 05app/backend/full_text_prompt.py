"""Prompt assembly for Full Text generation and user-controlled rewrites."""

from __future__ import annotations

import json

from .full_text_schema import (FULL_REWRITE_OUTPUT_SCHEMA, FULL_TEXT_OUTPUT_SCHEMA,
                               PAGE_REWRITE_OUTPUT_SCHEMA)


def _rag_payload(response: dict) -> list[dict]:
    return [{key: item[key] for key in
             ("text", "source_document", "rule_type", "verification_status", "priority")}
            for item in response.get("results", [])]


class FullTextPromptAssembler:
    def assemble(self, context: dict, selected_proposal: dict, plan: dict,
                 candidate_count: int) -> list[dict]:
        payload = {
            "task": {"type": "GENERATE_FULL_TEXT", "candidate_count": candidate_count,
                     "output_language": "English picture-book text"},
            "authoritative_database_facts": context["authoritative_database_facts"],
            "selected_proposal": selected_proposal,
            "pre_generation_language_plan": plan,
            "task_specific_rag_guidance": _rag_payload(context["rag_guidance"]),
            "historical_review_context": context["historical_review_context"],
            "teacher_instruction": plan.get("teacher_instruction", ""),
            "story_simplicity_budget": {
                "keep": ["one core problem", "one main plot line", "one main action loop",
                         "one small change or turn", "one clear ending"],
                "do_not_add": ["new character group", "new location", "second subplot",
                               "new cultural background", "new task system"],
                "expand_with": ["actions", "dialogue", "natural repetition", "visual details"],
            },
            "required_output_schema": FULL_TEXT_OUTPUT_SCHEMA,
        }
        system = (
            "You generate Full Text candidates inside Power Up Picture Book Forge (textbook basis: Cambridge "
            "Power Up 2). Workflow has already selected the "
            "Proposal and all resources. AUTHORITATIVE DATABASE FACTS are the only textbook facts; RAG is guidance "
            "only. Never query databases, RAG, SQL, or external sources. Return JSON only. Generate exactly the "
            "requested 2 or 3 complete English picture books, each with exactly the planned 8 or 12 pages. Target "
            "120–200 total words, 2–3 sentences per page, and sentences of about 10 words or fewer. Write character "
            "speech as script-style direct dialogue lines in the exact form 'Character Name: Dialogue.' (for example "
            "\"Big Elephant: You can't use your hands.\"), one speaker turn per line inside the page text. Never wrap "
            "speech in quotation marks and never use reporting clauses such as 'says X', 'X says', or 'he says'. "
            "Narration, actions, and scene description stay as plain standalone sentences without a leading name and "
            "colon (for example \"Little Monkey sits down.\"). A page may mix narration lines and dialogue lines "
            "naturally. Preserve the "
            "Proposal premise, causal chain, problem, and resolution direction. Do not add a second plot, new setting, "
            "new character group, cultural layer, or task system. Do not force vocabulary or patterns unnaturally. "
            "Candidate versions may vary in pacing, dialogue ratio, repetition placement, and ending presentation. "
            "Do not select a candidate, create a Draft, write Final data, or claim facts are verified."
        )
        return [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]


class RewritePromptAssembler:
    def assemble(self, current_draft: dict, selected_proposal: dict, plan: dict,
                 validation: dict, rag_guidance: dict, teacher_instruction: str,
                 scope: str, page_number: int | None = None,
                 locked_content: list[dict] | None = None) -> tuple[list[dict], dict]:
        schema = FULL_REWRITE_OUTPUT_SCHEMA if scope == "FULL" else PAGE_REWRITE_OUTPUT_SCHEMA
        payload = {
            "task": {"type": "REWRITE_FULL_TEXT" if scope == "FULL" else "REWRITE_PAGE",
                     "target_page_number": page_number},
            "current_draft": current_draft,
            "selected_proposal": selected_proposal,
            "pre_generation_language_plan": plan,
            "latest_validation_issues": validation.get("issues", []),
            "locked_content": locked_content or [],
            "relevant_rag_guidance": _rag_payload(rag_guidance),
            "teacher_instruction": teacher_instruction,
            "required_output_schema": schema,
        }
        system = (
            "You create a rewrite preview for the current Draft. Return JSON only. Preserve the selected Proposal "
            "skeleton and language plan. LOCKED CONTENT MUST REMAIN VERBATIM. Keep character speech in script-style "
            "direct dialogue lines in the exact form 'Character Name: Dialogue.', one speaker turn per line; never "
            "wrap speech in quotation marks and never use reporting clauses such as 'says X', 'X says', or 'he says'. "
            "Narration, actions, and scene description stay as plain standalone sentences without a leading name and "
            "colon; narration and dialogue lines may mix naturally on a page. Do not access external resources, add "
            "new plot lines, or claim facts are verified. For PAGE scope, return only the requested page and keep it "
            "causally consistent with adjacent pages. This is a preview: never overwrite a Draft or write Final data."
        )
        return ([{"role": "system", "content": system},
                 {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], schema)
