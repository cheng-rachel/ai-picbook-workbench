"""Context assembly without generation or LLM calls."""

from __future__ import annotations

from pathlib import Path

from .config import DATABASE_PATH
from .rag_service import LocalRagService
from .services import HistoricalVocabularyService, ReferenceDataService


class ContextPreparationService:
    def __init__(self, database_path: Path = DATABASE_PATH, rag: LocalRagService | None = None):
        self.reference = ReferenceDataService(database_path)
        self.history = HistoricalVocabularyService(database_path)
        self.rag = rag or LocalRagService()

    def prepare_proposal_context(self, topic_id: str | int, book_type: str) -> dict:
        topic = self.reference.get_topic_reference(topic_id)
        if topic is None:
            raise KeyError(f"Unknown topic: {topic_id}")
        level_id = topic["level_id"]
        if book_type == "ALL":
            responses = [self.rag.retrieve_for_proposal(level_id, code) for code in
                         ("TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR")]
            status = next((response["status"] for response in responses
                           if response["status"]["state"] != "READY"), responses[0]["status"])
            seen, combined = set(), []
            for response in responses:
                for item in response["results"]:
                    if item["chunk_id"] not in seen:
                        seen.add(item["chunk_id"])
                        combined.append(item)
            rag_guidance = {"status": status, "results": combined}
        else:
            rag_guidance = self.rag.retrieve_for_proposal(level_id, book_type)
        return {
            "authoritative_database_facts": {
                "topic": {key: topic[key] for key in (
                    "topic_id", "level_id", "semester", "unit_number", "topic_number",
                    "unit_title", "theme", "essential_question", "grammar_text",
                    "cross_curricular_text", "literature_text")},
                "textbook_words": topic["textbook_words"],
                "textbook_structures": topic["textbook_structures"],
                "textbook_examples": topic["textbook_examples"],
                "level_rules": self.reference.get_level_rules(level_id),
                "book_types": self.reference.get_book_types(),
            },
            "rag_guidance": rag_guidance,
            "historical_context": {
                "historical_vocabulary_usage": [],
                "topic_final_progress": self.history.get_topic_final_progress(topic["topic_id"]),
                "review_candidates": self.history.get_review_candidates(level_id, topic["topic_id"]),
            },
        }

    def prepare_full_text_context(self, topic_id: str | int, book_type: str) -> dict:
        topic = self.reference.get_topic_reference(topic_id)
        if topic is None:
            raise KeyError(f"Unknown topic: {topic_id}")
        level_id = topic["level_id"]
        return {
            "authoritative_database_facts": {
                "topic": {key: topic[key] for key in (
                    "topic_id", "level_id", "semester", "unit_number", "topic_number",
                    "unit_title", "theme", "essential_question", "grammar_text",
                    "cross_curricular_text", "literature_text")},
                "textbook_words": topic["textbook_words"],
                "textbook_structures": topic["textbook_structures"],
                "textbook_examples": topic["textbook_examples"],
                "level_rules": self.reference.get_level_rules(level_id),
                "book_type": book_type,
            },
            "rag_guidance": self.rag.retrieve_for_full_text(level_id, book_type),
            "historical_review_context": self.history.get_review_candidates(level_id, topic["topic_id"]),
        }

    def prepare_rewrite_guidance(self, topic_id: str | int, book_type: str,
                                 issue_types: list[str]) -> dict:
        topic = self.reference.get_topic_reference(topic_id)
        if topic is None:
            raise KeyError(f"Unknown topic: {topic_id}")
        return self.rag.retrieve_for_rewrite(topic["level_id"], issue_types, book_type)


def prepare_proposal_context(topic_id: str | int, book_type: str) -> dict:
    return ContextPreparationService().prepare_proposal_context(topic_id, book_type)
