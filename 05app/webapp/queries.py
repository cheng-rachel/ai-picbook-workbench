"""Read-only view queries for the Web UI.

This module only assembles display data. All business rules stay in the
backend workflows (M1–M5); nothing here mutates state or re-implements rules.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.database import connect
from backend.finalization_workflow import FinalizationWorkflow
from backend.full_text_workflow import FullTextWorkflow
from backend.services import HistoricalVocabularyService, ReferenceDataService


def list_topics(database_path: Path) -> dict:
    history = HistoricalVocabularyService(database_path)
    with connect(database_path) as db:
        topics = [dict(row) for row in db.execute(
            """SELECT topic_id,topic_number,semester,unit_number,unit_title,theme,
                      essential_question
               FROM topics ORDER BY topic_number""")]
        vocabulary_counts = {row["role"]: row["count"] for row in db.execute(
            """SELECT v.role AS role,COUNT(DISTINCT v.lemma) AS count
               FROM final_book_vocabulary v JOIN final_books b ON b.book_id=v.book_id
               WHERE b.is_current=1 GROUP BY v.role""")}
    for topic in topics:
        topic["final_progress"] = history.get_topic_final_progress(topic["topic_id"])
    return {"topics": topics,
            "system_vocabulary": {
                "core_lemmas": vocabulary_counts.get("CORE", 0),
                "extension_lemmas": vocabulary_counts.get("EXTENSION", 0),
                "review_lemmas": vocabulary_counts.get("REVIEW", 0),
                "note": "按 lemma 统计，暂未区分 multiword / 一词多义",
            }}


def topic_workspace(database_path: Path, topic_id: str) -> dict | None:
    reference = ReferenceDataService(database_path)
    topic = reference.get_topic_reference(topic_id)
    if topic is None:
        return None
    with connect(database_path) as db:
        # Manual proposals are wrapped in an internal single-proposal batch;
        # they surface as projects directly, not in the selection list.
        batches = [dict(row) for row in db.execute(
            """SELECT proposal_batch_id,target_book_type,original_proposal_count,
                      selected_count,discarded_count,selection_finalized_at,created_at,
                      teacher_input_json
               FROM proposal_batches WHERE topic_id=? ORDER BY created_at DESC""",
            (topic["topic_id"],))]
        batches = [batch for batch in batches
                   if json.loads(batch.pop("teacher_input_json") or "{}")
                   .get("source") != "MANUAL"]
        for batch in batches:
            batch["proposals"] = []
            for row in db.execute(
                    """SELECT proposal_id,project_id,proposal_index,payload_json,status
                       FROM proposals WHERE proposal_batch_id=? ORDER BY proposal_index""",
                    (batch["proposal_batch_id"],)):
                payload = json.loads(row["payload_json"])
                batch["proposals"].append({
                    "proposal_id": row["proposal_id"],
                    "project_id": row["project_id"],
                    "proposal_index": row["proposal_index"],
                    "status": row["status"],
                    "title": payload.get("title"),
                    "entry_point_cn": payload.get("entry_point_cn"),
                    "storyline": payload.get("storyline"),
                    "book_type": payload.get("book_type"),
                    "predicted_core_words": payload.get("predicted_core_words", []),
                    "predicted_core_patterns": payload.get("predicted_core_patterns", []),
                    "predicted_extension_words": payload.get("predicted_extension_words", []),
                })
        projects = [dict(row) for row in db.execute(
            """SELECT project_id,working_title,status,selected_proposal_id,current_draft_id,
                      created_at FROM projects WHERE topic_id=? ORDER BY created_at""",
            (topic["topic_id"],))]
        for project in projects:
            project["stage"] = _project_stage(db, project)
    return {
        "topic": {key: topic[key] for key in
                  ("topic_id", "topic_number", "semester", "unit_number", "unit_title",
                   "theme", "essential_question", "grammar_text",
                   "cross_curricular_text", "literature_text")},
        "textbook_words": topic["textbook_words"],
        "textbook_structures": topic["textbook_structures"],
        "textbook_examples": topic["textbook_examples"][:6],
        "batches": batches,
        "projects": projects,
    }


def _project_stage(db, project: dict) -> str:
    if project["status"] == "FINAL":
        return "FINAL"
    if project["current_draft_id"]:
        return "DRAFT"
    plan = db.execute(
        """SELECT status FROM pre_generation_plans WHERE project_id=? AND active=1
           ORDER BY updated_at DESC LIMIT 1""", (project["project_id"],)).fetchone()
    if plan and plan["status"] == "READY":
        has_candidates = db.execute(
            "SELECT COUNT(*) FROM full_text_candidates WHERE project_id=?",
            (project["project_id"],)).fetchone()[0]
        return "CANDIDATES" if has_candidates else "PLAN_READY"
    return "PLAN"


def project_state(database_path: Path, project_id: str) -> dict | None:
    with connect(database_path) as db:
        project = db.execute("SELECT * FROM projects WHERE project_id=?",
                             (project_id,)).fetchone()
        if not project:
            return None
        project = dict(project)
        proposal_row = db.execute(
            "SELECT payload_json,status FROM proposals WHERE proposal_id=?",
            (project["selected_proposal_id"],)).fetchone()
        proposal = json.loads(proposal_row["payload_json"]) if proposal_row else None
        plan_row = db.execute(
            """SELECT * FROM pre_generation_plans WHERE project_id=? AND active=1
               ORDER BY updated_at DESC LIMIT 1""", (project_id,)).fetchone()
        plan = None
        if plan_row:
            plan = {key: plan_row[key] for key in
                    ("plan_id", "status", "page_count", "generation_orientation",
                     "teacher_instruction")}
            plan["review_candidates"] = json.loads(plan_row["review_candidates_json"])
            plan["vocabulary"] = [dict(item) for item in db.execute(
                """SELECT raw_form,lemma,role,source_lookup_status,manual_review_required,
                          teacher_confirmed FROM planned_vocabulary WHERE plan_id=?
                   ORDER BY sequence_no""", (plan_row["plan_id"],))]
            plan["patterns"] = [dict(item) for item in db.execute(
                """SELECT raw_pattern,source_relation,teacher_confirmed
                   FROM planned_patterns WHERE plan_id=? ORDER BY sequence_no""",
                (plan_row["plan_id"],))]
        candidates = []
        for row in db.execute(
                """SELECT candidate_id,candidate_batch_id,candidate_index,title,page_count,
                          total_word_count,status,validation_json
                   FROM full_text_candidates WHERE project_id=?
                   ORDER BY created_at DESC,candidate_index""", (project_id,)):
            validation = json.loads(row["validation_json"])
            candidates.append({
                "candidate_id": row["candidate_id"],
                "candidate_batch_id": row["candidate_batch_id"],
                "candidate_index": row["candidate_index"],
                "title": row["title"], "page_count": row["page_count"],
                "total_word_count": row["total_word_count"], "status": row["status"],
                "validation_summary": validation.get("summary", {}),
                "pages": [dict(page) for page in db.execute(
                    """SELECT page_number,page_text AS text FROM full_text_candidate_pages
                       WHERE candidate_id=? ORDER BY page_number""",
                    (row["candidate_id"],))],
            })
        latest_batch = candidates[0]["candidate_batch_id"] if candidates else None
        candidates = [item for item in candidates
                      if item["candidate_batch_id"] == latest_batch]
        final_book = None
        if project["status"] == "FINAL":
            book = db.execute(
                """SELECT book_id,title,finalized_at FROM final_books
                   WHERE project_id=? AND is_current=1""", (project_id,)).fetchone()
            final_book = dict(book) if book else None
        preview_row = None
        confirmation_row = None
        if project["current_draft_id"]:
            preview_row = db.execute(
                """SELECT rewrite_preview_id,scope,target_page_number,teacher_instruction,
                          output_json,validation_json,base_content_hash,created_at
                   FROM rewrite_previews WHERE draft_id=? AND status='PREVIEW'
                   ORDER BY created_at DESC LIMIT 1""",
                (project["current_draft_id"],)).fetchone()
            confirmation_row = db.execute(
                """SELECT snapshot_json,content_hash FROM vocabulary_confirmations
                   WHERE draft_id=? AND active=1""",
                (project["current_draft_id"],)).fetchone()

    draft = None
    if project["current_draft_id"]:
        draft = FullTextWorkflow(database_path=database_path).get_current_draft(project_id)
    gate = None
    if draft and project["status"] != "FINAL":
        gate = FinalizationWorkflow(database_path=database_path).get_final_gate(project_id)

    # Overlay partially saved teacher decisions so a refresh never loses them.
    # Display merge only; the authoritative snapshot lives in the confirmation row.
    if draft and confirmation_row and \
            confirmation_row["content_hash"] == draft["content_hash"]:
        confirmed = {(entry["normalized_form"], entry["lemma"]): entry
                     for entry in json.loads(confirmation_row["snapshot_json"])["entries"]}
        for observation in (draft.get("validation") or {}).get("vocabulary_observations", []):
            entry = confirmed.get((observation["normalized_form"], observation["lemma"]))
            if entry and entry["teacher_confirmed"]:
                observation["teacher_confirmed"] = True
                observation["confirmed_role"] = entry["confirmed_role"]

    rewrite_preview = None
    if draft and preview_row and \
            preview_row["base_content_hash"] == draft["content_hash"]:
        preview_validation = json.loads(preview_row["validation_json"])
        rewrite_preview = {
            "rewrite_preview_id": preview_row["rewrite_preview_id"],
            "scope": preview_row["scope"],
            "target_page_number": preview_row["target_page_number"],
            "teacher_instruction": preview_row["teacher_instruction"],
            "output": json.loads(preview_row["output_json"]),
            "overall_status": preview_validation.get("overall_status"),
            "validation_summary": preview_validation.get("summary", {}),
            "created_at": preview_row["created_at"],
        }

    with connect(database_path) as db:
        stage = _project_stage(db, project)
    return {"project": {key: project[key] for key in
                        ("project_id", "topic_id", "working_title", "status",
                         "current_draft_id")},
            "stage": stage, "proposal": proposal, "plan": plan,
            "candidates": candidates, "draft": draft, "final_gate": gate,
            "final_book": final_book, "rewrite_preview": rewrite_preview}


def library(database_path: Path) -> dict:
    with connect(database_path) as db:
        books = []
        for row in db.execute(
                """SELECT b.book_id,b.project_id,b.topic_id,b.book_type_code,b.title,
                          b.finalized_at,b.is_current,t.theme
                   FROM final_books b JOIN topics t ON t.topic_id=b.topic_id
                   ORDER BY b.finalized_at DESC"""):
            book = dict(row)
            book["vocabulary"] = [dict(item) for item in db.execute(
                """SELECT raw_form,lemma,role,token_count FROM final_book_vocabulary
                   WHERE book_id=? ORDER BY role,raw_form""", (row["book_id"],))]
            books.append(book)
    return {"books": books}


def book_detail(database_path: Path, book_id: str) -> dict | None:
    with connect(database_path) as db:
        row = db.execute("SELECT * FROM final_books WHERE book_id=?", (book_id,)).fetchone()
        if not row:
            return None
        book = dict(row)
    book["snapshot"] = json.loads(book.pop("content_snapshot_json"))
    return book
