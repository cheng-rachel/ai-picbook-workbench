from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))

from backend.config import DOCS_DIR, ModelSettings  # noqa: E402
from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.full_text_workflow import FullTextWorkflow  # noqa: E402
from backend.model_adapter import ModelResult  # noqa: E402
from backend.repository import normalize_lemma  # noqa: E402


def sample_pages(page_count: int = 8) -> list[dict]:
    texts = [
        "Ben has a ball beside the garden gate. He wants to bounce a ball today.",
        "The ball rolls away from his waiting hands. Ben walks slowly and brings it back.",
        "He watches the ball and bends his knees. How many? Ben bounces it once.",
        "The ball rolls away again, but Ben waits. He moves closer to the little wall.",
        "Ben tries to bounce a ball very softly. How many? He counts one and two.",
        "His friend Mia taps a quiet steady beat. Ben follows the beat with both hands.",
        "Ben can bounce a ball beside the wall. How many? He counts three, four, five.",
        "Mia smiles at him.\nMia: Good job!\nBen gives her the ball for another turn.",
        "They walk together beneath the tall green trees. Ben keeps the ball near his feet.",
        "A small bird sings while they move ahead. Mia watches the path beside the pond.",
        "Ben finds a safe place and tries again. The ball returns softly to his hand.",
        "They wave goodbye and carry the ball home. Tomorrow they will play another quiet game.",
    ]
    return [{"page_number": index + 1, "text": texts[index]} for index in range(page_count)]


def candidate_payload(count: int = 2, page_count: int = 8,
                      requires_fact_verification: bool = False) -> dict:
    return {"candidates": [{
        "candidate_index": index + 1,
        "title": f"Ben and the Ball {index + 1}",
        "page_count": page_count,
        "pages": sample_pages(page_count),
        "generation_orientation": "BALANCED",
        "requires_fact_verification": requires_fact_verification,
    } for index in range(count)]}


def dialogue_sample_pages() -> list[dict]:
    """Script-format pages: 'Name: Dialogue' speaker lines mixed with narration."""
    texts = [
        "Ben holds a small red ball by the garden wall.\nMia: Can you bounce a ball today?",
        "Ben: I want to try it slowly today.\nBen taps the ball softly with one hand.",
        "Mia: How many?\nBen: Only one and two this time.\nMia claps for her happy friend.",
        "The ball rolls away to the low wall.\nBen walks over and brings it back.\nMia: Good job!",
        "Ben: I can bounce a ball by the wall now.\nMia: How many?\nBen: One, two, and three.",
        "Mia: Good job!\nBen smiles and gives the red ball to her.\nBen: Your turn now.",
        "Mia tries to bounce a ball by the wall.\nBen: How many?\nMia: One and two for me.",
        "Ben: Good job!\nThey put the ball away after the fun game.\nMia: We can play again tomorrow.",
    ]
    return [{"page_number": index + 1, "text": text} for index, text in enumerate(texts)]


def dialogue_candidate_payload(count: int = 2) -> dict:
    return {"candidates": [{
        "candidate_index": index + 1,
        "title": f"Ben and Mia Bounce {index + 1}",
        "page_count": 8,
        "pages": dialogue_sample_pages(),
        "requires_fact_verification": False,
    } for index in range(count)]}


def page_rewrite(text: str) -> dict:
    return {"page_number": 1, "text": text, "requires_fact_verification": False}


def full_rewrite(title: str = "A Gentler Ball") -> dict:
    pages = sample_pages()
    pages[1]["text"] = "Ben pauses beside the gate. He listens to Mia's quiet beat."
    return {"title": title, "pages": pages, "requires_fact_verification": False}


class FakeAdapter:
    def __init__(self, results: list[ModelResult]):
        self.results = list(results)
        self.calls = []

    def generate(self, task_type, messages, output_schema, model_config):
        self.calls.append({"task_type": task_type, "messages": messages,
                           "output_schema": output_schema, "model_config": model_config})
        return self.results.pop(0)


class M4WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "m4.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.project_id = "project-m4"
        self.proposal_id = "proposal-m4"
        now = datetime.now(timezone.utc).isoformat()
        proposal = {
            "proposal_index": 1, "title": "Ben Learns to Bounce",
            "entry_point_cn": "Ben在花园里学拍球。",
            "storyline": "Ben第一次拍球时，球总从手边滚走。他先停下来观察，再把动作放慢。朋友帮他数节奏，最后球能稳稳回到手边。",
            "predicted_core_words": ["bounce a ball", "have to / don't have to"],
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
                VALUES ('batch-m4','L2-T08','ALL','{}',1,'{}',1,0,NULL,?)""", (now,))
            db.execute("""INSERT INTO projects
                (project_id,topic_id,status,selected_proposal_id,created_at,updated_at)
                VALUES (?,'L2-T08','ACTIVE',?,?,?)""",
                       (self.project_id, self.proposal_id, now, now))
            db.execute("""INSERT INTO proposals
                (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,status,created_at,updated_at)
                VALUES (?,?, 'batch-m4',1,?,'SELECTED',?,?)""",
                       (self.proposal_id, self.project_id, json.dumps(proposal, ensure_ascii=False), now, now))
        self.settings = ModelSettings("fake", "", None, "fake-default", "fake-proposal",
                                      "fake-full", "fake-rewrite", 1)

    def tearDown(self):
        self.temp.cleanup()

    def workflow(self, adapter: FakeAdapter | None = None) -> FullTextWorkflow:
        return FullTextWorkflow(adapter=adapter or FakeAdapter([]), database_path=self.db,
                                settings=self.settings)

    def select_and_plan(self, workflow: FullTextWorkflow, **kwargs) -> dict:
        plan = workflow.prepare_generation_plan(self.project_id, 8, **kwargs)
        self.assertTrue(plan["ok"], plan)
        self.assertEqual("DRAFT", plan["status"])
        confirmed = workflow.confirm_generation_plan(plan["plan_id"])
        self.assertTrue(confirmed["ok"], confirmed)
        return confirmed

    def generate(self, workflow: FullTextWorkflow, plan: dict, count: int = 2) -> dict:
        result = workflow.generate_full_text_candidates(plan["plan_id"], count)
        self.assertTrue(result["ok"], result)
        return result

    def vocabulary_snapshot(self, draft_id: str, teacher_confirmed: bool = True) -> dict:
        with connect(self.db) as db:
            rows = db.execute("""SELECT raw_form,normalized_form,lemma,source_lookup_status,
                planned_role,classification_state FROM draft_vocab_observations
                WHERE draft_id=? AND classification_state='NEEDS_REVIEW' ORDER BY rowid""",
                              (draft_id,)).fetchall()
        return {"entries": [{
            "raw_form": row["raw_form"], "normalized_form": row["normalized_form"],
            "lemma": row["lemma"], "source_status": row["source_lookup_status"],
            "classification_state": row["classification_state"],
            "confirmed_role": "NON_TEACHING_CONTEXT",
            "teacher_confirmed": teacher_confirmed,
        } for row in rows]}

    def test_established_project_is_required_and_selection_is_already_fixed(self):
        workflow = self.workflow()
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db) as db:
            db.execute("""INSERT INTO projects(project_id,topic_id,status,created_at,updated_at)
                          VALUES ('unestablished','L2-T08','ACTIVE',?,?)""", (now, now))
        blocked = workflow.prepare_generation_plan("unestablished", 8)
        self.assertEqual("PROPOSAL_NOT_SELECTED", blocked["error_code"])
        selected = workflow.select_proposal(self.project_id, self.proposal_id)
        self.assertTrue(selected["ok"])
        with connect(self.db) as db:
            self.assertEqual("SELECTED", db.execute(
                "SELECT status FROM proposals WHERE proposal_id=?", (self.proposal_id,)).fetchone()[0])
            self.assertEqual(self.proposal_id, db.execute(
                "SELECT selected_proposal_id FROM projects WHERE project_id=?", (self.project_id,)).fetchone()[0])

    def test_plan_separates_words_patterns_extension_review_and_rechecks_sources(self):
        workflow = self.workflow()
        plan = self.select_and_plan(workflow)
        core = {item["raw_form"] for item in plan["planned_core_words"]}
        patterns = {item["normalized_pattern"] for item in plan["planned_core_patterns"]}
        self.assertEqual({"bounce a ball"}, core)
        self.assertIn("how many", patterns)
        self.assertIn("good job", patterns)
        # A predicted "word" that is actually a Unit 8 textbook structure is
        # promoted into the pattern list instead of staying a core word.
        self.assertIn("have to don't have to", patterns)
        promoted = next(item for item in plan["planned_core_patterns"]
                        if item["normalized_pattern"] == "have to don't have to")
        self.assertEqual("TEXTBOOK", promoted["source_relation"])
        self.assertNotIn("have to / don't have to", core)
        # "bounce a ball" is a synthetic teacher word outside the Power Up 2
        # textbook scope, so the source recheck marks it UNRESOLVED.
        self.assertEqual("UNRESOLVED", plan["planned_core_words"][0]["source_lookup_status"])
        self.assertEqual(["sticker"], [item["raw_form"] for item in plan["planned_extension_words"]])
        self.assertEqual([], plan["planned_review_words"])
        self.assertEqual(0, plan["review_candidates"]["pool_size"])
        self.assertEqual("BALANCED", plan["generation_orientation"])
        self.assertTrue(all(item["teacher_confirmed"] for item in plan["planned_vocabulary"]))
        self.assertTrue(all(item["teacher_confirmed"] for item in plan["planned_core_patterns"]))

    def test_proposal_predictions_create_draft_unconfirmed_plan_until_teacher_confirmation(self):
        workflow = self.workflow()
        plan = workflow.prepare_generation_plan(self.project_id, 8)
        self.assertEqual("DRAFT", plan["status"])
        self.assertTrue(all(not item["teacher_confirmed"] for item in plan["planned_vocabulary"]))
        self.assertTrue(all(not item["teacher_confirmed"] for item in plan["planned_core_patterns"]))
        blocked = workflow.generate_full_text_candidates(plan["plan_id"])
        self.assertEqual("PLAN_NOT_READY", blocked["error_code"])
        ready = workflow.confirm_generation_plan(plan["plan_id"])
        self.assertEqual("READY", ready["status"])

    def test_page_count_and_candidate_count_are_explicitly_bounded(self):
        workflow = self.workflow()
        self.assertEqual("INVALID_PAGE_COUNT",
                         workflow.prepare_generation_plan(self.project_id, 10)["error_code"])
        plan = workflow.prepare_generation_plan(self.project_id, 8)
        self.assertEqual("INVALID_CANDIDATE_COUNT",
                         workflow.generate_full_text_candidates(plan["plan_id"], 1)["error_code"])
        self.assertEqual("INVALID_CANDIDATE_COUNT",
                         workflow.generate_full_text_candidates(plan["plan_id"], 4)["error_code"])

    def test_generates_two_candidates_with_layered_prompt_but_no_automatic_draft(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        result = self.generate(workflow, plan, 2)
        self.assertEqual(2, result["candidate_count"])
        self.assertEqual("FULL_TEXT", fake.calls[0]["task_type"])
        prompt = json.loads(fake.calls[0]["messages"][1]["content"])
        self.assertEqual({"task", "authoritative_database_facts", "selected_proposal",
                          "pre_generation_language_plan", "task_specific_rag_guidance",
                          "historical_review_context", "teacher_instruction",
                          "story_simplicity_budget", "required_output_schema"}, set(prompt))
        with connect(self.db) as db:
            self.assertEqual(2, db.execute("SELECT COUNT(*) FROM full_text_candidates").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM draft_versions").fetchone()[0])
            self.assertIsNone(db.execute("SELECT current_draft_id FROM projects WHERE project_id=?",
                                         (self.project_id,)).fetchone()[0])

    def test_default_candidate_count_is_three_and_explicit_three_is_supported(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(3), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        result = workflow.generate_full_text_candidates(plan["plan_id"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(3, result["candidate_count"])

    def test_candidate_orientation_is_inherited_from_ready_plan_not_model_output(self):
        payload = candidate_payload(3)
        payload["candidates"][0].pop("generation_orientation")
        payload["candidates"][1]["generation_orientation"] = "LANGUAGE"
        payload["candidates"][2]["generation_orientation"] = "STORY"
        fake = FakeAdapter([ModelResult(True, json.dumps(payload, ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        result = workflow.generate_full_text_candidates(plan["plan_id"])
        self.assertTrue(result["ok"], result)
        self.assertEqual(1, result["attempts"])
        self.assertEqual({"BALANCED"},
                         {item["generation_orientation"] for item in result["candidates"]})
        with connect(self.db) as db:
            saved = {row[0] for row in db.execute(
                "SELECT generation_orientation FROM full_text_candidates WHERE plan_id=?",
                (plan["plan_id"],),
            )}
        self.assertEqual({"BALANCED"}, saved)
        candidate_schema = fake.calls[0]["output_schema"]["properties"]["candidates"]["items"]
        self.assertNotIn("generation_orientation", candidate_schema["required"])
        self.assertNotIn("generation_orientation", candidate_schema["properties"])

    def test_schema_failure_returns_safe_attempt_diagnostics_without_persistence(self):
        invalid_semantic = candidate_payload(3)
        invalid_semantic["candidates"][0]["pages"][0]["text"] = 123
        fake = FakeAdapter([
            ModelResult(True, "not-json", provider_metadata={"model": "fake-full"}),
            ModelResult(True, json.dumps(invalid_semantic, ensure_ascii=False),
                        provider_metadata={"model": "fake-full"}),
        ])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        result = workflow.generate_full_text_candidates(plan["plan_id"])
        self.assertFalse(result["ok"])
        self.assertEqual("INVALID_SCHEMA", result["error_code"])
        self.assertEqual(2, result["attempts"])
        diagnostics = result["schema_failure_attempts"]
        self.assertEqual(2, len(diagnostics))
        self.assertEqual("fake-full", diagnostics[0]["provider_model"])
        self.assertEqual(1, diagnostics[0]["attempt_number"])
        self.assertEqual("not-json", diagnostics[0]["raw_response_content"])
        self.assertEqual("INVALID_JSON", diagnostics[0]["parse_error"]["code"])
        self.assertIsNone(diagnostics[0]["schema_validation_error"])
        self.assertEqual(2, diagnostics[1]["attempt_number"])
        self.assertIsNone(diagnostics[1]["parse_error"])
        self.assertEqual("INVALID_SCHEMA",
                         diagnostics[1]["schema_validation_error"]["code"])
        self.assertEqual("$.candidates[0].pages[0].text",
                         diagnostics[1]["failed_field_path"])
        with connect(self.db) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM full_text_candidates").fetchone()[0])

    def test_candidate_selection_creates_current_draft_and_autosave_updates_current_state(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidates = self.generate(workflow, plan)["candidates"]
        selected = workflow.select_candidate_as_draft(candidates[0]["candidate_id"])
        self.assertTrue(selected["ok"], selected)
        draft = selected["draft"]
        self.assertEqual(candidates[0]["candidate_id"], draft["source_candidate_id"])
        self.assertEqual("DRAFT", draft["status"])
        confirmation = workflow.confirm_vocabulary(
            draft["draft_id"], self.vocabulary_snapshot(draft["draft_id"]))
        self.assertTrue(confirmation["active"])
        self.assertTrue(confirmation["ready_for_final"])
        changed = [dict(page) for page in draft["pages"]]
        changed[0]["text"] = "Ben holds the ball. He waits beside the gate."
        saved = workflow.autosave_draft(draft["draft_id"], changed)
        self.assertTrue(saved["ok"])
        self.assertEqual(changed[0]["text"], saved["draft"]["pages"][0]["text"])
        self.assertEqual(0, saved["draft"]["vocabulary_confirmation"]["active"])

    def test_vocabulary_confirmation_preserves_source_and_requires_only_needs_review(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow, planned_extension_words=["mysteryword"])
        candidate = self.generate(workflow, plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        snapshot = self.vocabulary_snapshot(draft["draft_id"])
        saved = workflow.confirm_vocabulary(draft["draft_id"], snapshot)
        self.assertTrue(saved["ok"], saved)
        self.assertTrue(saved["ready_for_final"])
        self.assertNotIn(("VAL-UNCLASSIFIED-001", "BLOCKER"), {
            (item["rule_key"], item["severity"])
            for item in workflow.get_current_draft(self.project_id)["validation"]["issues"]})
        changed_source = self.vocabulary_snapshot(draft["draft_id"])
        changed_source["entries"][0]["source_status"] = "UNRESOLVED"
        if changed_source["entries"][0]["source_status"] == snapshot["entries"][0]["source_status"]:
            changed_source["entries"][0]["source_status"] = "TEXTBOOK"
        self.assertEqual("SOURCE_STATUS_IMMUTABLE",
                         workflow.confirm_vocabulary(draft["draft_id"], changed_source)["error_code"])
        incomplete = self.vocabulary_snapshot(draft["draft_id"], teacher_confirmed=False)
        status = workflow.confirm_vocabulary(draft["draft_id"], incomplete)
        self.assertFalse(status["ready_for_final"])
        self.assertTrue(status["unconfirmed_entries"])

    def test_warning_acknowledgement_is_scoped_to_one_validation_run(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        warning = next(item for item in draft["validation_issues"] if item["severity"] == "WARNING")
        acknowledged = workflow.acknowledge_validation_issue(warning["issue_id"])
        self.assertEqual("ACKNOWLEDGED", acknowledged["resolution_status"])
        workflow.autosave_draft(draft["draft_id"], draft["pages"])
        current = workflow.get_current_draft(self.project_id)
        self.assertTrue(current["validation_issues"])
        self.assertTrue(all(item["resolution_status"] == "OPEN"
                            for item in current["validation_issues"]))
        with connect(self.db) as db:
            self.assertEqual("ACKNOWLEDGED", db.execute(
                "SELECT resolution_status FROM validation_issues WHERE issue_id=?",
                (warning["issue_id"],)).fetchone()[0])

    def test_validation_reports_structure_language_vocabulary_and_cold_start_without_rewrite(self):
        workflow = self.workflow()
        plan = self.select_and_plan(workflow, planned_review_words=["red"])
        pages = sample_pages(8)
        pages[0]["text"] = "This sentence contains far more than ten separate English words for young children today."
        pages[1]["text"] = ""
        validation = workflow.validator.validate(pages, plan,
                                                 workflow.reference.get_topic_reference(8))
        issue_map = {(issue["rule_key"], issue["severity"]) for issue in validation["issues"]}
        self.assertIn(("VAL-BLANK-PAGE-001", "BLOCKER"), issue_map)
        self.assertIn(("VAL-WORDCOUNT-001", "WARNING"), issue_map)
        self.assertIn(("VAL-SENT-LEN-001", "WARNING"), issue_map)
        self.assertIn(("VAL-PAGE-SENT-001", "WARNING"), issue_map)
        self.assertIn(("VAL-REVIEW-001", "INFO"), issue_map)
        self.assertIn(("VAL-UNCLASSIFIED-001", "BLOCKER"), issue_map)
        bounce = next(item for item in validation["vocabulary_observations"]
                      if item["raw_form"] == "bounce a ball")
        how_many = next(item for item in validation["pattern_observations"]
                        if item["normalized_pattern"] == "how many")
        self.assertEqual(2, bounce["token_count"])
        self.assertEqual(3, how_many["matched_count"])

    def test_detector_calibration_covers_patterns_contractions_names_and_planned_inflections(self):
        self.assertEqual("let's", normalize_lemma("let's"))
        self.assertEqual("go", normalize_lemma("goes"))
        workflow = self.workflow()
        plan = self.select_and_plan(
            workflow,
            planned_core_words=["jump rope"],
            planned_extension_words=["turn"],
            planned_core_patterns=["I’ll try again.", "Good job!"],
        )
        pages = [
            {"page_number": 1, "text": "I’ll try again, says Rabbit. Duoduo smiles."},
            {"page_number": 2, "text": "Duoduo turns the rope. Rabbit says, Good job!"},
            {"page_number": 3, "text": "I’ll try again. Duoduo can’t jump rope."},
            {"page_number": 4, "text": "Let’s turn together. Rabbit watches Duoduo."},
            {"page_number": 5, "text": "Duoduo jumps near the rope. Duoduo's shoe waits near the garden's gate."},
            {"page_number": 6, "text": "I’ll try again. Duoduo turns slowly."},
            {"page_number": 7, "text": "Rabbit says, Good job! Duoduo nods."},
            {"page_number": 8, "text": "Good job! Rabbit waves to Duoduo."},
        ]
        validation = workflow.validator.validate(
            pages, plan, workflow.reference.get_topic_reference(8))
        unclassified = {item["raw_form"] for item in validation["vocabulary_observations"]
                        if item["detected_status"] == "UNCLASSIFIED"}
        self.assertTrue({"jump", "rope"}.issubset(unclassified))
        self.assertTrue({"i'll", "try", "good", "job", "can't", "let's",
                         "let'", "duoduo", "duoduo's", "rabbit", "turn"}.isdisjoint(unclassified))
        self.assertIn("garden's", unclassified)
        turn = next(item for item in validation["vocabulary_observations"]
                    if item["raw_form"] == "turn" and item["detected_status"] == "PLANNED")
        self.assertEqual(3, turn["token_count"])
        patterns = {item["normalized_pattern"]: item["matched_count"]
                    for item in validation["pattern_observations"]}
        self.assertEqual(3, patterns["i'll try again"])
        self.assertEqual(3, patterns["good job"])

    def test_script_dialogue_pages_flow_through_workflow_without_label_side_effects(self):
        dialogue_rewrite = {
            "page_number": 3,
            "text": "Mia: How many can you do now?\nBen: One, two, and three today.\n"
                    "Mia claps for her happy friend.",
            "requires_fact_verification": False,
        }
        fake = FakeAdapter([
            ModelResult(True, json.dumps(dialogue_candidate_payload(2), ensure_ascii=False)),
            ModelResult(True, json.dumps(dialogue_rewrite, ensure_ascii=False)),
        ])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        # The generation prompt enforces the script-dialogue format at the source.
        self.assertIn("Character Name: Dialogue", fake.calls[0]["messages"][0]["content"])

        validation = candidate["validation"]
        # Speaker labels are structural markers: excluded from word and sentence metrics.
        self.assertEqual(123, validation["metrics"]["total_word_count"])
        self.assertEqual([2, 2, 3, 3, 3, 3, 3, 3],
                         [page["sentence_count"]
                          for page in validation["metrics"]["page_sentences"]])
        codes = {issue["rule_key"] for issue in validation["issues"]}
        self.assertTrue({"VAL-WORDCOUNT-001", "VAL-PAGE-SENT-001",
                         "VAL-SENT-LEN-001"}.isdisjoint(codes))
        # Line-initial label names never reach the vocabulary scan, while planned
        # words and patterns still match inside the dialogue text itself.
        observed = {item["raw_form"] for item in validation["vocabulary_observations"]}
        self.assertTrue({"ben", "mia"}.isdisjoint(observed))
        bounce = next(item for item in validation["vocabulary_observations"]
                      if item["raw_form"] == "bounce a ball")
        self.assertEqual(3, bounce["token_count"])
        patterns = {item["normalized_pattern"]: item
                    for item in validation["pattern_observations"]}
        self.assertEqual(3, patterns["how many"]["matched_count"])
        self.assertEqual([4, 6, 8], patterns["good job"]["matched_pages"])

        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        # A PAGE rewrite keeps the script format verbatim through preview + accept.
        preview = workflow.create_rewrite_preview(draft["draft_id"], "PAGE",
                                                  "保持剧本式对话。", 3)
        self.assertTrue(preview["ok"], preview)
        self.assertIn("Character Name: Dialogue", fake.calls[1]["messages"][0]["content"])
        accepted = workflow.accept_rewrite_preview(preview["rewrite_preview_id"])
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual(dialogue_rewrite["text"], accepted["draft"]["pages"][2]["text"])
        self.assertEqual(126, accepted["validation"]["metrics"]["total_word_count"])

        # Only genuine content words require review; confirming them clears the blocker.
        confirmation = workflow.confirm_vocabulary(
            draft["draft_id"], self.vocabulary_snapshot(draft["draft_id"]))
        self.assertTrue(confirmation["ok"], confirmation)
        self.assertTrue(confirmation["ready_for_final"])
        current = workflow.get_current_draft(self.project_id)
        self.assertNotIn("VAL-UNCLASSIFIED-001",
                         {issue["rule_key"] for issue in current["validation"]["issues"]})
        for issue in current["validation_issues"]:
            if issue["severity"] == "WARNING" and issue["resolution_status"] == "OPEN":
                self.assertTrue(
                    workflow.acknowledge_validation_issue(issue["issue_id"])["ok"])

    def test_classification_states_and_blocker_only_cover_unconfirmed_needs_review(self):
        workflow = self.workflow()
        plan = self.select_and_plan(workflow, planned_core_words=["jump rope"],
                                    planned_extension_words=["turn"])
        validation = workflow.validator.validate(
            sample_pages(), plan, workflow.reference.get_topic_reference(8))
        by_state = {}
        for item in validation["vocabulary_observations"]:
            by_state.setdefault(item["classification_state"], []).append(item)
        self.assertTrue(by_state["PLANNED"])
        self.assertTrue(by_state["KNOWN_UNPLANNED"])
        self.assertTrue(by_state["NEEDS_REVIEW"])
        self.assertTrue(all(item["source_lookup_status"] in
                            {"TEXTBOOK", "TEXTBOOK_SCOPE"}
                            for item in by_state["KNOWN_UNPLANNED"]))
        self.assertTrue(all(item["source_lookup_status"] == "UNRESOLVED"
                            for item in by_state["NEEDS_REVIEW"]))
        blocker = next(item for item in validation["issues"]
                       if item["rule_key"] == "VAL-UNCLASSIFIED-001")
        self.assertIn(str(len(by_state["NEEDS_REVIEW"])), blocker["message"])

    def test_known_and_unresolved_vocabulary_promotions_create_plan_revision(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        first = self.select_and_plan(workflow)
        candidate = self.generate(workflow, first)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        with connect(self.db) as db:
            rows = [dict(row) for row in db.execute("""SELECT * FROM draft_vocab_observations
                WHERE draft_id=? AND classification_state IN ('KNOWN_UNPLANNED','NEEDS_REVIEW')
                ORDER BY classification_state LIMIT 2""", (draft["draft_id"],))]
        selections = [{"normalized_form": row["normalized_form"], "role": "CORE"}
                      for row in rows]
        before_sources = {row["normalized_form"]: row["source_lookup_status"] for row in rows}
        revision = workflow.revise_generation_plan_from_vocabulary(draft["draft_id"], selections)
        self.assertTrue(revision["ok"], revision)
        self.assertEqual("DRAFT", revision["status"])
        self.assertNotEqual(first["plan_id"], revision["plan_id"])
        ready = workflow.confirm_generation_plan(revision["plan_id"])
        self.assertEqual("READY", ready["status"])
        promoted = {item["normalized_form"]: item for item in ready["planned_vocabulary"]}
        for normalized, source in before_sources.items():
            self.assertEqual(source, promoted[normalized]["source_lookup_status"])
        current = workflow.get_current_draft(self.project_id)
        states = {item["normalized_form"]: item["classification_state"]
                  for item in current["validation"]["vocabulary_observations"]}
        for normalized in before_sources:
            self.assertEqual("PLANNED", states[normalized])

    def test_consecutive_promotions_extend_pending_revision_until_confirmed(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        ready_plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, ready_plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        with connect(self.db) as db:
            rows = [dict(row) for row in db.execute("""SELECT * FROM draft_vocab_observations
                WHERE draft_id=? AND classification_state IN ('KNOWN_UNPLANNED','NEEDS_REVIEW')
                ORDER BY classification_state LIMIT 2""", (draft["draft_id"],))]
        self.assertEqual(2, len(rows))
        word_a, word_b = rows[0]["normalized_form"], rows[1]["normalized_form"]

        first = workflow.revise_generation_plan_from_vocabulary(
            draft["draft_id"], [{"normalized_form": word_a, "role": "EXTENSION"}])
        self.assertTrue(first["ok"], first)
        self.assertEqual("DRAFT", first["status"])
        # The active plan is now a pending DRAFT revision; a second promotion
        # must extend it instead of failing with PLAN_NOT_READY.
        second = workflow.revise_generation_plan_from_vocabulary(
            draft["draft_id"], [{"normalized_form": word_b, "role": "REVIEW"}])
        self.assertTrue(second["ok"], second)
        self.assertNotEqual(first["plan_id"], second["plan_id"])
        by_word = {item["normalized_form"]: item["role"]
                   for item in second["planned_vocabulary"]}
        self.assertEqual("EXTENSION", by_word[word_a])
        self.assertEqual("REVIEW", by_word[word_b])

        ready = workflow.confirm_generation_plan(second["plan_id"])
        self.assertEqual("READY", ready["status"])
        current = workflow.get_current_draft(self.project_id)
        states = {item["normalized_form"]: item["classification_state"]
                  for item in current["validation"]["vocabulary_observations"]}
        self.assertEqual("PLANNED", states[word_a])
        self.assertEqual("PLANNED", states[word_b])

        # Guard unchanged: without any teacher-confirmed READY Plan in history,
        # promotion is still rejected.
        with connect(self.db) as db:
            db.execute("UPDATE pre_generation_plans SET status='DRAFT' WHERE project_id=?",
                       (self.project_id,))
        rejected = workflow.revise_generation_plan_from_vocabulary(
            draft["draft_id"], [{"normalized_form": word_a, "role": "CORE"}])
        self.assertEqual("PLAN_NOT_READY", rejected["error_code"])

    def test_plan_change_invalidates_confirmation_without_rewriting_candidate_audit(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        with connect(self.db) as db:
            audit_before = db.execute("SELECT validation_json FROM full_text_candidates WHERE candidate_id=?",
                                      (candidate["candidate_id"],)).fetchone()[0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        confirmation = workflow.confirm_vocabulary(
            draft["draft_id"], self.vocabulary_snapshot(draft["draft_id"]))
        self.assertTrue(confirmation["active"])
        with connect(self.db) as db:
            known = db.execute("""SELECT normalized_form FROM draft_vocab_observations
                WHERE draft_id=? AND classification_state='KNOWN_UNPLANNED' LIMIT 1""",
                               (draft["draft_id"],)).fetchone()[0]
        revision = workflow.revise_generation_plan_from_vocabulary(
            draft["draft_id"], [{"normalized_form": known, "role": "REVIEW"}])
        workflow.confirm_generation_plan(revision["plan_id"])
        with connect(self.db) as db:
            self.assertEqual(0, db.execute(
                "SELECT active FROM vocabulary_confirmations WHERE confirmation_id=?",
                (confirmation["confirmation_id"],)).fetchone()[0])
            self.assertEqual(audit_before, db.execute(
                "SELECT validation_json FROM full_text_candidates WHERE candidate_id=?",
                (candidate["candidate_id"],)).fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM recurrence_events").fetchone()[0])

    def test_extension_absence_is_warning_and_non_teaching_is_not_a_plan_role(self):
        workflow = self.workflow()
        rejected = workflow.prepare_generation_plan(
            self.project_id, 8, non_teaching_context_words=["garden"])
        self.assertEqual("NON_TEACHING_NOT_PLAN_ROLE", rejected["error_code"])
        plan = self.select_and_plan(workflow, planned_extension_words=["sticker"])
        validation = workflow.validator.validate(sample_pages(), plan,
                                                 workflow.reference.get_topic_reference(8))
        codes = {issue["rule_key"] for issue in validation["issues"]}
        self.assertIn("VAL-EXT-001", codes)

    def test_invalid_page_count_is_a_blocker_but_draft_is_still_saved(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2, 7), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidates = self.generate(workflow, plan)["candidates"]
        self.assertEqual("BLOCKED", candidates[0]["validation"]["overall_status"])
        selected = workflow.select_candidate_as_draft(candidates[0]["candidate_id"])
        self.assertTrue(selected["ok"], selected)
        codes = {issue["rule_key"] for issue in selected["draft"]["validation"]["issues"]}
        self.assertIn("VAL-PAGE-001", codes)
        with connect(self.db) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM draft_versions").fetchone()[0])

    def test_unresolved_planned_vocabulary_and_historical_conflict_are_warnings(self):
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.db) as db:
            db.execute("INSERT INTO projects(project_id,topic_id,status,created_at,updated_at) VALUES ('history-project','L2-T08','ACTIVE',?,?)", (now, now))
            db.execute("""INSERT INTO draft_versions
                (draft_id,project_id,version_number,status,content_hash,created_at,updated_at)
                VALUES ('history-draft','history-project',1,'DRAFT','hash',?,?)""", (now, now))
            db.execute("""INSERT INTO final_books
                (book_id,project_id,draft_id,topic_id,book_type_code,title,content_snapshot_json,
                 finalized_at,is_current) VALUES
                ('history-book','history-project','history-draft','L2-T08','TEXTBOOK_SYNC','History','{}',?,1)""", (now,))
            db.execute("""INSERT INTO final_book_vocabulary
                (final_book_vocab_id,book_id,raw_form,lemma,role,token_count)
                VALUES ('history-vocab','history-book','bounce a ball','bounce a ball','CORE',3)""")
        workflow = self.workflow()
        plan = self.select_and_plan(workflow, planned_core_words=["bounce a ball", "mysteryword"])
        validation = workflow.validator.validate(sample_pages(), plan,
                                                 workflow.reference.get_topic_reference(8))
        codes = {issue["rule_key"] for issue in validation["issues"]}
        self.assertIn("VAL-HISTORY-001", codes)
        self.assertIn("VAL-VOCAB-SOURCE-001", codes)

    def test_rewrite_preview_cancel_and_accept_preserve_human_control(self):
        fake = FakeAdapter([
            ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False)),
            ModelResult(True, json.dumps(page_rewrite("Ben waits quietly. He taps the ball once."), ensure_ascii=False)),
            ModelResult(True, json.dumps(page_rewrite("Ben waits and smiles. He bounces the ball softly."), ensure_ascii=False)),
        ])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        original_text = draft["pages"][0]["text"]
        preview = workflow.create_rewrite_preview(draft["draft_id"], "PAGE", "Make it quieter", 1)
        self.assertTrue(preview["ok"], preview)
        self.assertFalse(preview["draft_overwritten"])
        self.assertEqual(original_text, workflow.get_current_draft(self.project_id)["pages"][0]["text"])
        cancelled = workflow.cancel_rewrite_preview(preview["rewrite_preview_id"])
        self.assertTrue(cancelled["draft_unchanged"])
        accepted_preview = workflow.create_rewrite_preview(draft["draft_id"], "PAGE",
                                                           "Show a gentle bounce", 1)
        accepted = workflow.accept_rewrite_preview(accepted_preview["rewrite_preview_id"])
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual("Ben waits and smiles. He bounces the ball softly.",
                         accepted["draft"]["pages"][0]["text"])

    def test_full_rewrite_is_preview_then_overwrites_only_after_accept(self):
        fake = FakeAdapter([
            ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False)),
            ModelResult(True, json.dumps(full_rewrite(), ensure_ascii=False)),
        ])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        before = draft["pages"][1]["text"]
        preview = workflow.create_rewrite_preview(draft["draft_id"], "FULL",
                                                  "Use quieter visual details")
        self.assertEqual(before, workflow.get_current_draft(self.project_id)["pages"][1]["text"])
        accepted = workflow.accept_rewrite_preview(preview["rewrite_preview_id"])
        self.assertEqual("ACCEPTED", accepted["status"])
        self.assertEqual("Ben pauses beside the gate. He listens to Mia's quiet beat.",
                         accepted["draft"]["pages"][1]["text"])
        self.assertEqual("A Gentler Ball", workflow.get_current_draft(self.project_id)["title"])

    def test_fact_verification_is_manual_and_becomes_stale_after_autosave(self):
        fake = FakeAdapter([ModelResult(
            True, json.dumps(candidate_payload(2, requires_fact_verification=True), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        draft = workflow.select_candidate_as_draft(candidate["candidate_id"])["draft"]
        self.assertEqual("REQUIRED", draft["fact_review"]["status"])
        verified = workflow.update_fact_review(draft["draft_id"], "VERIFIED_BY_USER",
                                               "Teacher checked the factual statement.")
        self.assertEqual("VERIFIED_BY_USER", verified["status"])
        pages = [dict(page) for page in draft["pages"]]
        pages[0]["text"] += " Ben looks outside."
        saved = workflow.autosave_draft(draft["draft_id"], pages)
        self.assertEqual("REQUIRED", saved["draft"]["fact_review"]["status"])
        self.assertIsNone(saved["draft"]["fact_review"]["verification_note"])

    def test_candidate_and_draft_never_write_final_or_recurrence(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        workflow.select_candidate_as_draft(candidate["candidate_id"])
        with connect(self.db) as db:
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM final_books").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM final_book_vocabulary").fetchone()[0])
            self.assertEqual(0, db.execute("SELECT COUNT(*) FROM recurrence_events").fetchone()[0])

    def test_static_rebuild_preserves_m4_runtime_state(self):
        fake = FakeAdapter([ModelResult(True, json.dumps(candidate_payload(2), ensure_ascii=False))])
        workflow = self.workflow(fake)
        plan = self.select_and_plan(workflow)
        candidate = self.generate(workflow, plan)["candidates"][0]
        workflow.select_candidate_as_draft(candidate["candidate_id"])
        with connect(self.db) as db:
            before = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("projects", "proposal_batches", "proposals",
                                    "pre_generation_plans", "full_text_candidates",
                                    "draft_versions", "validation_runs", "validation_issues")}
        build_database(self.db, extract_all(DOCS_DIR))
        with connect(self.db) as db:
            after = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in before}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
