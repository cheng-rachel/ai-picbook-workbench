"""M5 backend workflow: Final Gate, Final Book transaction, and recurrence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from .config import DATABASE_PATH
from .database import connect

TEACHING_ROLES = ("CORE", "EXTENSION", "REVIEW")
VALID_BOOK_TYPES = {"TEXTBOOK_SYNC", "THEME_EXTENSION", "CROSS_CURRICULAR"}
# Per-unit current-Final quota: 03语言项目收录标准 gives Level 2 = 63 册 / 9 单元 = 7 册。
# Per-type split confirmed by human decision (2026-08-19):
# 教材衔接 2 / 主题拓展 3 / 跨学科提升 2.
TOPIC_TOTAL_LIMIT = 7
BOOK_TYPE_LIMITS = {"TEXTBOOK_SYNC": 2, "THEME_EXTENSION": 3, "CROSS_CURRICULAR": 2}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinalizationWorkflow:
    def __init__(self, database_path: Path = DATABASE_PATH):
        self.database_path = Path(database_path)

    def get_final_gate(self, project_id: str) -> dict:
        """Read-only Final Gate report; never writes anything."""
        state = self._load_final_state(project_id)
        if "error_code" in state:
            return {"ok": False, **state}
        return {"ok": True, "project_id": project_id,
                "ready": not state["blockers"], "blockers": state["blockers"],
                "checks": state["checks"]}

    def finalize_book(self, project_id: str) -> dict:
        state = self._load_final_state(project_id)
        if "error_code" in state:
            return {"ok": False, **state}
        if state["blockers"]:
            return {"ok": False, "error_code": "FINAL_GATE_BLOCKED",
                    "message": "Final Gate has unresolved blockers",
                    "blockers": state["blockers"]}

        project = state["project"]
        draft = state["draft"]
        plan = state["plan"]
        now = _now()
        book_id = "book-" + uuid4().hex
        vocabulary_rows = state["teaching_vocabulary"]
        recurrence_rows = [item for item in vocabulary_rows
                           if item["role"] == "REVIEW" and item["token_count"] >= 1]
        snapshot = {
            "book_id": book_id,
            "title": project["working_title"],
            "book_type": state["book_type"],
            "topic_id": project["topic_id"],
            "level_id": state["level_id"],
            "draft_id": draft["draft_id"],
            "plan_id": plan["plan_id"],
            "generation_orientation": plan["generation_orientation"],
            "page_count": len(draft["pages"]),
            "pages": draft["pages"],
            "total_word_count": state["validation"]["metrics"]["total_word_count"],
            "content_hash": draft["content_hash"],
            "validation_run_id": state["validation_run_id"],
            "rule_version": state["validation"].get("rule_version"),
            "planned_patterns": [item["raw_pattern"] for item in plan["planned_core_patterns"]],
            "teaching_vocabulary": vocabulary_rows,
            "vocabulary_confirmation_snapshot": state["confirmation_snapshot"],
            "fact_review": state["fact_review"],
            "finalized_at": now,
        }
        with connect(self.database_path) as db:
            db.execute("""INSERT INTO final_books
                (book_id,project_id,draft_id,topic_id,book_type_code,title,
                 content_snapshot_json,finalized_at,is_current,superseded_by_book_id,book_number)
                VALUES (?,?,?,?,?,?,?,?,1,NULL,NULL)""",
                       (book_id, project_id, draft["draft_id"], project["topic_id"],
                        state["book_type"], project["working_title"] or "",
                        json.dumps(snapshot, ensure_ascii=False), now))
            for item in vocabulary_rows:
                db.execute("""INSERT INTO final_book_vocabulary
                    (final_book_vocab_id,book_id,raw_form,lemma,role,token_count)
                    VALUES (?,?,?,?,?,?)""",
                           ("final-vocab-" + uuid4().hex, book_id, item["raw_form"],
                            item["lemma"], item["role"], item["token_count"]))
            for item in recurrence_rows:
                db.execute("""INSERT INTO recurrence_events
                    (recurrence_event_id,book_id,level_id,lemma,token_count_in_book,
                     event_value,is_active,created_at) VALUES (?,?,?,?,?,1,1,?)""",
                           ("recurrence-" + uuid4().hex, book_id, state["level_id"],
                            item["lemma"], item["token_count"], now))
            # Link an earlier withdrawn Final of this project to its replacement.
            db.execute("""UPDATE final_books SET superseded_by_book_id=?
                          WHERE project_id=? AND book_id<>? AND is_current=0
                          AND superseded_by_book_id IS NULL""",
                       (book_id, project_id, book_id))
            db.execute("UPDATE projects SET status='FINAL',updated_at=? WHERE project_id=?",
                       (now, project_id))
            db.execute("UPDATE draft_versions SET status='FINAL',updated_at=? WHERE draft_id=?",
                       (now, draft["draft_id"]))
        return {"ok": True, "book_id": book_id, "project_id": project_id,
                "title": project["working_title"], "book_type": state["book_type"],
                "final_vocabulary": vocabulary_rows,
                "recurrence_events": [{"lemma": item["lemma"],
                                       "token_count_in_book": item["token_count"]}
                                      for item in recurrence_rows],
                "finalized_at": now}

    def unfinalize_book(self, book_id: str) -> dict:
        """Withdraw a Final: deactivate statistics without deleting history."""
        now = _now()
        with connect(self.database_path) as db:
            book = db.execute("SELECT * FROM final_books WHERE book_id=?", (book_id,)).fetchone()
            if not book:
                return self._failure("BOOK_NOT_FOUND", "Final Book not found")
            if not book["is_current"]:
                return self._failure("BOOK_NOT_CURRENT", "Final Book is already withdrawn")
            db.execute("UPDATE final_books SET is_current=0 WHERE book_id=?", (book_id,))
            db.execute("UPDATE recurrence_events SET is_active=0 WHERE book_id=?", (book_id,))
            db.execute("UPDATE projects SET status='ACTIVE',updated_at=? WHERE project_id=?",
                       (now, book["project_id"]))
            db.execute("UPDATE draft_versions SET status='DRAFT',updated_at=? WHERE draft_id=?",
                       (now, book["draft_id"]))
        return {"ok": True, "book_id": book_id, "project_id": book["project_id"],
                "is_current": False, "project_status": "ACTIVE"}

    def _load_final_state(self, project_id: str) -> dict:
        blockers: list[dict] = []

        def block(code: str, message: str) -> None:
            blockers.append({"code": code, "message": message})

        with connect(self.database_path) as db:
            project = db.execute("SELECT * FROM projects WHERE project_id=?",
                                 (project_id,)).fetchone()
            if not project:
                return self._failure("PROJECT_NOT_FOUND", "Project not found")
            if project["status"] == "FINAL":
                return self._failure("PROJECT_ALREADY_FINAL",
                                     "Project already has a current Final; withdraw it first")
            if not project["current_draft_id"]:
                return self._failure("NO_CURRENT_DRAFT", "Project has no Current Draft")
            draft = dict(db.execute("SELECT * FROM draft_versions WHERE draft_id=?",
                                    (project["current_draft_id"],)).fetchone())
            draft["pages"] = [dict(row) for row in db.execute(
                """SELECT page_number,page_text AS text FROM draft_pages
                   WHERE draft_id=? ORDER BY page_number""", (draft["draft_id"],))]
            topic = db.execute("SELECT level_id FROM topics WHERE topic_id=?",
                               (project["topic_id"],)).fetchone()
            proposal = db.execute("SELECT payload_json FROM proposals WHERE proposal_id=?",
                                  (project["selected_proposal_id"],)).fetchone()
            latest = db.execute(
                """SELECT validation_run_id,content_hash,result_json FROM validation_runs
                   WHERE draft_id=? ORDER BY created_at DESC,validation_run_id DESC LIMIT 1""",
                (draft["draft_id"],)).fetchone()
            issues = [dict(row) for row in db.execute(
                "SELECT * FROM validation_issues WHERE validation_run_id=?",
                (latest["validation_run_id"],))] if latest else []
            ready_plan = db.execute(
                """SELECT plan_id FROM pre_generation_plans
                   WHERE project_id=? AND active=1 AND status='READY'
                   ORDER BY updated_at DESC LIMIT 1""", (project_id,)).fetchone()
            confirmation = db.execute(
                """SELECT * FROM vocabulary_confirmations
                   WHERE draft_id=? AND active=1
                   ORDER BY confirmed_at DESC LIMIT 1""", (draft["draft_id"],)).fetchone()
            fact = db.execute("SELECT * FROM fact_reviews WHERE draft_id=?",
                              (draft["draft_id"],)).fetchone()
            observations = {row["normalized_form"]: dict(row) for row in db.execute(
                "SELECT * FROM draft_vocab_observations WHERE draft_id=?", (draft["draft_id"],))}

        book_type = json.loads(proposal["payload_json"]).get("book_type") if proposal else None
        if book_type not in VALID_BOOK_TYPES:
            return self._failure("INVALID_BOOK_TYPE", "Selected Proposal has no valid book type")

        # 1. Current Validation Run with zero blockers.
        validation = json.loads(latest["result_json"]) if latest else None
        if not latest or latest["content_hash"] != draft["content_hash"]:
            block("VALIDATION_STALE", "Current Draft has no Validation Run for its latest content")
            validation = None
        else:
            open_blockers = [item for item in issues if item["severity"] == "BLOCKER"]
            if open_blockers:
                block("VALIDATION_BLOCKED",
                      f"Latest Validation Run has {len(open_blockers)} blocker issue(s)")
            # 2. Every remaining Warning acknowledged or resolved.
            open_warnings = [item for item in issues if item["severity"] == "WARNING"
                             and item["resolution_status"] == "OPEN"]
            if open_warnings:
                block("WARNINGS_UNRESOLVED",
                      f"{len(open_warnings)} Warning(s) must be acknowledged or resolved")

        # 3. Active READY Plan and a valid vocabulary confirmation bound to it.
        confirmation_snapshot = None
        if not ready_plan:
            block("PLAN_NOT_READY", "Project has no active READY Plan")
        elif not confirmation:
            block("VOCABULARY_UNCONFIRMED", "No active vocabulary confirmation for Current Draft")
        elif confirmation["content_hash"] != draft["content_hash"] or \
                confirmation["plan_id"] != ready_plan["plan_id"]:
            block("VOCABULARY_CONFIRMATION_STALE",
                  "Vocabulary confirmation does not match current text and READY Plan")
        else:
            confirmation_snapshot = json.loads(confirmation["snapshot_json"])
            readiness = confirmation_snapshot.get("readiness", {})
            if not readiness.get("ready_for_final"):
                block("VOCABULARY_UNCONFIRMED", "Vocabulary confirmation is not ready for Final")

        # 4. Fact verification complete for the current text.
        if not fact or fact["status"] == "REQUIRED":
            block("FACT_VERIFICATION_REQUIRED", "Fact verification is not complete")
        elif fact["content_hash"] != draft["content_hash"]:
            block("FACT_VERIFICATION_STALE", "Fact review does not match the current text")
        elif fact["status"] == "VERIFIED_BY_USER" and not (fact["verification_note"] or "").strip():
            block("VERIFICATION_NOTE_REQUIRED", "Teacher verification note is required")

        # 5. Topic Final quota (upper bounds block; lower bounds are topic progress).
        with connect(self.database_path) as db:
            counts = {row["book_type_code"]: row["count"] for row in db.execute(
                """SELECT book_type_code,COUNT(*) AS count FROM final_books
                   WHERE topic_id=? AND is_current=1 GROUP BY book_type_code""",
                (project["topic_id"],))}
        total = sum(counts.values())
        if total >= TOPIC_TOTAL_LIMIT:
            block("TOPIC_QUOTA_FULL",
                  f"Unit already has {total} current Finals (limit {TOPIC_TOTAL_LIMIT})")
        type_count = counts.get(book_type, 0)
        type_limit = BOOK_TYPE_LIMITS[book_type]
        if type_count >= type_limit:
            block("BOOK_TYPE_QUOTA_FULL",
                  f"Unit already has {type_count} current {book_type} Finals "
                  f"(limit {type_limit})")

        plan = self._load_plan(ready_plan["plan_id"]) if ready_plan else None
        teaching_vocabulary = []
        if plan:
            seen = set()
            for item in plan["planned_vocabulary"]:
                if item["role"] not in TEACHING_ROLES:
                    continue
                key = (item["lemma"], item["role"])
                if key in seen:
                    continue
                seen.add(key)
                observation = observations.get(item["normalized_form"])
                teaching_vocabulary.append({
                    "raw_form": item["raw_form"], "lemma": item["lemma"],
                    "role": item["role"],
                    "token_count": observation["token_count"] if observation else 0,
                })

        return {
            "project": dict(project), "draft": draft, "plan": plan,
            "book_type": book_type, "level_id": topic["level_id"],
            "validation": validation,
            "validation_run_id": latest["validation_run_id"] if latest else None,
            "confirmation_snapshot": confirmation_snapshot,
            "fact_review": dict(fact) if fact else None,
            "teaching_vocabulary": teaching_vocabulary,
            "blockers": blockers,
            "checks": {
                "validation_current": bool(latest and latest["content_hash"] == draft["content_hash"]),
                "blocker_count": len([item for item in issues if item["severity"] == "BLOCKER"]),
                "open_warning_count": len([item for item in issues
                                           if item["severity"] == "WARNING"
                                           and item["resolution_status"] == "OPEN"]),
                "vocabulary_confirmation_valid": confirmation_snapshot is not None and
                                                 bool(confirmation_snapshot.get("readiness", {})
                                                      .get("ready_for_final")),
                "fact_review_status": fact["status"] if fact else None,
                "book_type": book_type,
                "topic_current_finals": total,
            },
        }

    def _load_plan(self, plan_id: str) -> dict:
        with connect(self.database_path) as db:
            plan = dict(db.execute("SELECT * FROM pre_generation_plans WHERE plan_id=?",
                                   (plan_id,)).fetchone())
            plan["planned_vocabulary"] = [dict(item) for item in db.execute(
                """SELECT raw_form,normalized_form,lemma,role FROM planned_vocabulary
                   WHERE plan_id=? ORDER BY sequence_no""", (plan_id,))]
            plan["planned_core_patterns"] = [dict(item) for item in db.execute(
                """SELECT raw_pattern,normalized_pattern FROM planned_patterns
                   WHERE plan_id=? ORDER BY sequence_no""", (plan_id,))]
            return plan

    @staticmethod
    def _failure(code: str, message: str) -> dict:
        return {"ok": False, "error_code": code, "message": message}
