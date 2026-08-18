from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))
sys.path.insert(0, str(ROOT / "06tests"))

from backend.config import DOCS_DIR, ModelSettings  # noqa: E402
from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.finalization_workflow import FinalizationWorkflow  # noqa: E402
from backend.full_text_workflow import FullTextWorkflow  # noqa: E402
from backend.model_adapter import ModelResult  # noqa: E402
from backend.services import HistoricalVocabularyService  # noqa: E402

from test_m4_full_text import FakeAdapter, candidate_payload  # noqa: E402


class M5FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "m5.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.project_id = "project-m5"
        self.proposal_id = "proposal-m5"
        now = datetime.now(timezone.utc).isoformat()
        self.proposal = {
            "proposal_index": 1, "title": "Ben Learns to Bounce",
            "entry_point_cn": "Ben在花园里学拍球。",
            "storyline": "Ben第一次拍球时，球总从手边滚走。他先停下来观察，再把动作放慢。朋友帮他数节奏，最后球能稳稳回到手边。",
            "predicted_core_words": ["bounce a ball"],
            "predicted_core_patterns": ["How many?", "Good job!"],
            "predicted_extension_words": ["sticker"],
            "book_type": "TEXTBOOK_SYNC",
            "plot_structure": "球滚走—观察—放慢—找到节奏",
            "potential_issues": "保持动作安全。", "creative_highlight": "用节奏体现进步。",
        }
        with connect(self.db) as db:
            db.execute("""INSERT INTO proposal_batches
                (proposal_batch_id,topic_id,target_book_type,teacher_input_json,
                 original_proposal_count,evaluation_json,selected_count,discarded_count,
                 selection_finalized_at,created_at)
                VALUES ('batch-m5','L2-T08','ALL','{}',1,'{}',1,0,NULL,?)""", (now,))
            db.execute("""INSERT INTO projects
                (project_id,topic_id,status,selected_proposal_id,created_at,updated_at)
                VALUES (?,'L2-T08','ACTIVE',?,?,?)""",
                       (self.project_id, self.proposal_id, now, now))
            db.execute("""INSERT INTO proposals
                (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,status,created_at,updated_at)
                VALUES (?,?, 'batch-m5',1,?,'SELECTED',?,?)""",
                       (self.proposal_id, self.project_id,
                        json.dumps(self.proposal, ensure_ascii=False), now, now))
        self.settings = ModelSettings("fake", "", None, "fake-default", "fake-proposal",
                                      "fake-full", "fake-rewrite", 1)
        self.finalization = FinalizationWorkflow(database_path=self.db)

    def tearDown(self):
        self.temp.cleanup()

    def workflow(self, adapter: FakeAdapter | None = None) -> FullTextWorkflow:
        return FullTextWorkflow(adapter=adapter or FakeAdapter([]), database_path=self.db,
                                settings=self.settings)

    def build_current_draft(self, requires_fact_verification: bool = False,
                            planned_review_words: list[str] | None = None) -> tuple[FullTextWorkflow, str]:
        payload = candidate_payload(2, requires_fact_verification=requires_fact_verification)
        workflow = self.workflow(FakeAdapter(
            [ModelResult(True, json.dumps(payload, ensure_ascii=False))]))
        plan = workflow.prepare_generation_plan(
            self.project_id, 8, planned_review_words=planned_review_words)
        self.assertTrue(plan["ok"], plan)
        ready = workflow.confirm_generation_plan(plan["plan_id"])
        self.assertTrue(ready["ok"], ready)
        generated = workflow.generate_full_text_candidates(plan["plan_id"], 2)
        self.assertTrue(generated["ok"], generated)
        selected = workflow.select_candidate_as_draft(
            generated["candidates"][0]["candidate_id"])
        self.assertTrue(selected["ok"], selected)
        return workflow, selected["draft"]["draft_id"]

    def confirm_needs_review_as_non_teaching(self, workflow: FullTextWorkflow,
                                             draft_id: str) -> dict:
        with connect(self.db) as db:
            rows = db.execute("""SELECT raw_form,normalized_form,lemma,source_lookup_status,
                classification_state FROM draft_vocab_observations
                WHERE draft_id=? AND classification_state='NEEDS_REVIEW' ORDER BY rowid""",
                              (draft_id,)).fetchall()
        snapshot = {"entries": [{
            "raw_form": row["raw_form"], "normalized_form": row["normalized_form"],
            "lemma": row["lemma"], "source_status": row["source_lookup_status"],
            "classification_state": row["classification_state"],
            "confirmed_role": "NON_TEACHING_CONTEXT", "teacher_confirmed": True,
        } for row in rows]}
        result = workflow.confirm_vocabulary(draft_id, snapshot)
        self.assertTrue(result["ok"], result)
        return result

    def acknowledge_open_warnings(self, workflow: FullTextWorkflow, draft_id: str) -> None:
        with connect(self.db) as db:
            issues = db.execute("""SELECT issue_id FROM validation_issues
                WHERE severity='WARNING' AND resolution_status='OPEN' AND validation_run_id=
                (SELECT validation_run_id FROM validation_runs WHERE draft_id=?
                 ORDER BY created_at DESC,validation_run_id DESC LIMIT 1)""",
                              (draft_id,)).fetchall()
        for issue in issues:
            result = workflow.acknowledge_validation_issue(issue["issue_id"], "教师确认。")
            self.assertTrue(result["ok"], result)

    def make_final_ready(self, requires_fact_verification: bool = False,
                         planned_review_words: list[str] | None = None) -> tuple[FullTextWorkflow, str]:
        workflow, draft_id = self.build_current_draft(
            requires_fact_verification, planned_review_words)
        self.confirm_needs_review_as_non_teaching(workflow, draft_id)
        self.acknowledge_open_warnings(workflow, draft_id)
        return workflow, draft_id

    def test_final_gate_blocks_open_warnings_and_unconfirmed_vocabulary(self):
        self.build_current_draft()
        gate = self.finalization.get_final_gate(self.project_id)
        self.assertTrue(gate["ok"], gate)
        self.assertFalse(gate["ready"])
        codes = {item["code"] for item in gate["blockers"]}
        self.assertIn("VALIDATION_BLOCKED", codes)
        self.assertIn("WARNINGS_UNRESOLVED", codes)
        self.assertIn("VOCABULARY_UNCONFIRMED", codes)
        blocked = self.finalization.finalize_book(self.project_id)
        self.assertFalse(blocked["ok"])
        self.assertEqual("FINAL_GATE_BLOCKED", blocked["error_code"])
        with connect(self.db) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM final_books").fetchone()[0])

    def test_finalize_writes_teaching_vocabulary_and_review_recurrence_only(self):
        self.make_final_ready(planned_review_words=["ball"])
        result = self.finalization.finalize_book(self.project_id)
        self.assertTrue(result["ok"], result)
        with connect(self.db) as db:
            book = db.execute("SELECT * FROM final_books WHERE book_id=?",
                              (result["book_id"],)).fetchone()
            vocabulary = {(row["lemma"], row["role"]): row["token_count"] for row in db.execute(
                "SELECT lemma,role,token_count FROM final_book_vocabulary WHERE book_id=?",
                (result["book_id"],))}
            recurrence = {row["lemma"]: dict(row) for row in db.execute(
                "SELECT * FROM recurrence_events WHERE book_id=?", (result["book_id"],))}
            project_status = db.execute("SELECT status FROM projects WHERE project_id=?",
                                        (self.project_id,)).fetchone()[0]
            draft_status = db.execute("SELECT status FROM draft_versions WHERE draft_id=?",
                                      (book["draft_id"],)).fetchone()[0]
        self.assertEqual(1, book["is_current"])
        self.assertIsNone(book["book_number"])
        self.assertEqual("TEXTBOOK_SYNC", book["book_type_code"])
        self.assertEqual("FINAL", project_status)
        self.assertEqual("FINAL", draft_status)
        roles = {role for _, role in vocabulary}
        self.assertTrue(roles.issubset({"CORE", "EXTENSION", "REVIEW"}), roles)
        self.assertIn(("bounce a ball", "CORE"), vocabulary)
        self.assertIn(("sticker", "EXTENSION"), vocabulary)
        self.assertIn(("ball", "REVIEW"), vocabulary)
        self.assertGreaterEqual(vocabulary[("ball", "REVIEW")], 1)
        # KNOWN_UNPLANNED and NON_TEACHING_CONTEXT never enter the Final snapshot.
        snapshot_lemmas = {lemma for lemma, _ in vocabulary}
        with connect(self.db) as db:
            excluded = [row["lemma"] for row in db.execute(
                """SELECT lemma FROM draft_vocab_observations
                   WHERE draft_id=? AND classification_state IN ('KNOWN_UNPLANNED','NEEDS_REVIEW')""",
                (book["draft_id"],))]
        for lemma in excluded:
            self.assertNotIn(lemma, snapshot_lemmas)
        # Recurrence: REVIEW-only, one book-level event per lemma.
        self.assertEqual({"ball"}, set(recurrence))
        self.assertEqual(1, recurrence["ball"]["event_value"])
        self.assertEqual(1, recurrence["ball"]["is_active"])
        snapshot = json.loads(book["content_snapshot_json"])
        self.assertEqual(8, snapshot["page_count"])
        self.assertEqual(book["draft_id"], snapshot["draft_id"])

    def test_finalized_core_words_feed_next_book_review_candidates(self):
        self.make_final_ready()
        result = self.finalization.finalize_book(self.project_id)
        self.assertTrue(result["ok"], result)
        candidates = HistoricalVocabularyService(self.db).get_review_candidates(2, 8)
        self.assertEqual(1, candidates["pool_size"])
        entry = candidates["candidates"][0]
        self.assertEqual("bounce a ball", entry["lemma"])
        self.assertEqual(0, entry["current_book_recurrence_count"])
        self.assertEqual(3, entry["remaining_to_min"])
        self.assertEqual("CURRENT_FINAL", entry["historical_usage"][0]["final_status"])

    def test_fact_verification_required_blocks_until_verified_with_note(self):
        workflow, draft_id = self.make_final_ready(requires_fact_verification=True)
        gate = self.finalization.get_final_gate(self.project_id)
        self.assertIn("FACT_VERIFICATION_REQUIRED",
                      {item["code"] for item in gate["blockers"]})
        verified = workflow.update_fact_review(draft_id, "VERIFIED_BY_USER", "已人工核对事实。")
        self.assertTrue(verified["ok"], verified)
        result = self.finalization.finalize_book(self.project_id)
        self.assertTrue(result["ok"], result)

    def _insert_existing_finals(self, book_types):
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db) as db:
            draft_id = db.execute("SELECT current_draft_id FROM projects WHERE project_id=?",
                                  (self.project_id,)).fetchone()[0]
            for index, book_type in enumerate(book_types):
                db.execute("""INSERT INTO final_books
                    (book_id,project_id,draft_id,topic_id,book_type_code,title,
                     content_snapshot_json,finalized_at,is_current)
                    VALUES (?,?,?,?,?,?,'{}',?,1)""",
                           (f"book-existing-{index}", self.project_id, draft_id,
                            "L2-T08", book_type, f"Existing {index}", now))

    def test_unit_total_quota_blocks_final(self):
        # Power Up 2: 7 current Finals per unit (63 books / 9 units),
        # split 2 教材衔接 / 3 主题拓展 / 2 跨学科提升 (human decision 2026-08-19).
        self.make_final_ready()
        self._insert_existing_finals(["TEXTBOOK_SYNC"] * 2 + ["THEME_EXTENSION"] * 3 +
                                     ["CROSS_CURRICULAR"] * 2)
        blocked = self.finalization.finalize_book(self.project_id)
        self.assertFalse(blocked["ok"])
        self.assertIn("TOPIC_QUOTA_FULL",
                      {item["code"] for item in blocked["blockers"]})

    def test_book_type_quota_blocks_final_below_total(self):
        # Two existing TEXTBOOK_SYNC finals fill that type's quota (limit 2), so a
        # third TEXTBOOK_SYNC final is blocked even though the unit total (2) < 7.
        self.make_final_ready()
        self._insert_existing_finals(["TEXTBOOK_SYNC"] * 2)
        blocked = self.finalization.finalize_book(self.project_id)
        self.assertFalse(blocked["ok"])
        codes = {item["code"] for item in blocked["blockers"]}
        self.assertIn("BOOK_TYPE_QUOTA_FULL", codes)
        self.assertNotIn("TOPIC_QUOTA_FULL", codes)

    def test_below_type_quota_does_not_block(self):
        # One TEXTBOOK_SYNC final plus other types' finals (total 6) must not block
        # a second TEXTBOOK_SYNC final: other types don't consume this type's quota.
        self.make_final_ready()
        self._insert_existing_finals(["TEXTBOOK_SYNC"] + ["THEME_EXTENSION"] * 3 +
                                     ["CROSS_CURRICULAR"] * 2)
        result = self.finalization.finalize_book(self.project_id)
        self.assertTrue(result["ok"], result)

    def test_unfinalize_withdraws_statistics_and_allows_refinal(self):
        self.make_final_ready(planned_review_words=["ball"])
        first = self.finalization.finalize_book(self.project_id)
        self.assertTrue(first["ok"], first)
        again = self.finalization.finalize_book(self.project_id)
        self.assertEqual("PROJECT_ALREADY_FINAL", again["error_code"])

        withdrawn = self.finalization.unfinalize_book(first["book_id"])
        self.assertTrue(withdrawn["ok"], withdrawn)
        with connect(self.db) as db:
            self.assertEqual(0, db.execute(
                "SELECT is_current FROM final_books WHERE book_id=?",
                (first["book_id"],)).fetchone()[0])
            self.assertEqual(0, db.execute(
                "SELECT COUNT(*) FROM recurrence_events WHERE book_id=? AND is_active=1",
                (first["book_id"],)).fetchone()[0])
            self.assertEqual("ACTIVE", db.execute(
                "SELECT status FROM projects WHERE project_id=?",
                (self.project_id,)).fetchone()[0])
        # A withdrawn Final no longer feeds historical candidates.
        self.assertEqual(0, HistoricalVocabularyService(self.db)
                         .get_review_candidates(2, 8)["pool_size"])

        second = self.finalization.finalize_book(self.project_id)
        self.assertTrue(second["ok"], second)
        with connect(self.db) as db:
            superseded = db.execute(
                "SELECT superseded_by_book_id FROM final_books WHERE book_id=?",
                (first["book_id"],)).fetchone()[0]
        self.assertEqual(second["book_id"], superseded)

    def test_autosave_after_confirmation_invalidates_final_gate(self):
        workflow, draft_id = self.make_final_ready()
        with connect(self.db) as db:
            pages = [dict(row) for row in db.execute(
                """SELECT page_number,page_text AS text FROM draft_pages
                   WHERE draft_id=? ORDER BY page_number""", (draft_id,))]
        pages[0]["text"] = "Ben has a red ball beside the garden gate. He wants to bounce a ball today."
        saved = workflow.autosave_draft(draft_id, pages)
        self.assertTrue(saved["ok"], saved)
        gate = self.finalization.get_final_gate(self.project_id)
        self.assertFalse(gate["ready"])
        self.assertIn("VOCABULARY_UNCONFIRMED",
                      {item["code"] for item in gate["blockers"]})

    def test_final_project_draft_is_frozen_until_withdrawn(self):
        workflow, draft_id = self.make_final_ready()
        result = self.finalization.finalize_book(self.project_id)
        self.assertTrue(result["ok"], result)
        with connect(self.db) as db:
            pages = [dict(row) for row in db.execute(
                """SELECT page_number,page_text AS text FROM draft_pages
                   WHERE draft_id=? ORDER BY page_number""", (draft_id,))]
        pages[0]["text"] = "Ben has a red ball beside the garden gate. He wants to bounce a ball today."
        saved = workflow.autosave_draft(draft_id, pages)
        self.assertFalse(saved["ok"])
        self.assertEqual("PROJECT_FINAL", saved["error_code"])
        withdrawn = self.finalization.unfinalize_book(result["book_id"])
        self.assertTrue(withdrawn["ok"], withdrawn)
        saved = workflow.autosave_draft(draft_id, pages)
        self.assertTrue(saved["ok"], saved)


if __name__ == "__main__":
    unittest.main()
