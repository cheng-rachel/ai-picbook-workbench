"""Backend business services: the only supported access layer for Workflow/UI."""

from __future__ import annotations

from pathlib import Path

from .config import DATABASE_PATH
from .database import connect
from .repository import ReferenceRepository, normalize_lemma


class ReferenceDataService:
    def __init__(self, database_path: Path = DATABASE_PATH):
        self.database_path = Path(database_path)
        self.repository = ReferenceRepository(self.database_path)

    def get_topic_reference(self, topic_id: str | int) -> dict | None:
        return self.repository.get_topic(topic_id)

    def get_level_rules(self, level_id: int) -> dict:
        return self.repository.get_level_rules(level_id)

    def get_textbook_examples(self, topic_id: str | int) -> list[dict]:
        topic = self.repository.get_topic(topic_id)
        return [] if topic is None else topic["textbook_examples"]

    def lookup_textbook_entry(self, form_or_lemma: str) -> list[dict]:
        return self.repository.lookup_textbook_entry(form_or_lemma)

    def get_book_types(self) -> list[dict]:
        with connect(self.database_path) as db:
            return [dict(row) for row in db.execute(
                "SELECT code,display_name_zh,core_positioning FROM book_types WHERE active=1 ORDER BY code")]


class HistoricalVocabularyService:
    def __init__(self, database_path: Path = DATABASE_PATH):
        self.database_path = Path(database_path)

    def get_historical_vocab_usage(self, lemma: str, level_id: int = 2) -> list[dict]:
        canonical = normalize_lemma(lemma)
        with connect(self.database_path) as db:
            rows = db.execute("""
                SELECT v.lemma, t.topic_id, t.topic_number, t.semester, t.unit_number,
                       b.title, v.role AS historical_role,
                       CASE WHEN b.is_current=1 THEN 'CURRENT_FINAL' ELSE 'INACTIVE_FINAL' END AS final_status
                FROM final_book_vocabulary v
                JOIN final_books b ON b.book_id=v.book_id
                JOIN topics t ON t.topic_id=b.topic_id
                WHERE v.lemma=? AND t.level_id=?
                ORDER BY b.finalized_at, b.book_id
            """, (canonical, level_id)).fetchall()
            return [dict(row) for row in rows]

    def get_review_candidates(self, level_id: int, topic_id: str | int) -> dict:
        topic_key = f"L2-T{int(topic_id):02d}" if str(topic_id).isdigit() else str(topic_id)
        with connect(self.database_path) as db:
            rows = db.execute("""
                SELECT DISTINCT v.lemma
                FROM final_book_vocabulary v
                JOIN final_books b ON b.book_id=v.book_id
                JOIN topics t ON t.topic_id=b.topic_id
                WHERE b.is_current=1 AND t.level_id=? AND v.role='CORE'
                ORDER BY v.lemma
            """, (level_id,)).fetchall()
            candidates = []
            for row in rows:
                lemma = row["lemma"]
                recurrence = db.execute("""
                    SELECT COUNT(*) FROM recurrence_events
                    WHERE level_id=? AND lemma=? AND is_active=1
                """, (level_id, lemma)).fetchone()[0]
                candidates.append({
                    "lemma": lemma,
                    "current_book_recurrence_count": recurrence,
                    "target_min": 3,
                    "target_max": 5,
                    "remaining_to_min": max(0, 3 - recurrence),
                    "historical_usage": self.get_historical_vocab_usage(lemma, level_id),
                })
        size = len(candidates)
        recommendation = 0 if size == 0 else size if size <= 4 else min(size, 6)
        return {"level_id": level_id, "topic_id": topic_key, "pool_size": size,
                "recommended_count_max": recommendation, "warning_required": False,
                "candidates": candidates}

    def get_topic_final_progress(self, topic_id: str | int) -> dict:
        topic_key = f"L2-T{int(topic_id):02d}" if str(topic_id).isdigit() else str(topic_id)
        with connect(self.database_path) as db:
            counts = {row["book_type_code"]: row["count"] for row in db.execute("""
                SELECT book_type_code, COUNT(*) AS count FROM final_books
                WHERE topic_id=? AND is_current=1 GROUP BY book_type_code
            """, (topic_key,))}
        return {"topic_id": topic_key, "total_current_finals": sum(counts.values()),
                "by_book_type": {code: counts.get(code, 0) for code in
                                 ("TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR")}}
