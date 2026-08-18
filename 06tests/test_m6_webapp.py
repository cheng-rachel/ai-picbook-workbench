from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))
sys.path.insert(0, str(ROOT / "06tests"))

from backend.config import DOCS_DIR, ModelSettings  # noqa: E402
from backend.database import build_database, connect  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.full_text_workflow import FullTextWorkflow  # noqa: E402
from backend.model_adapter import ModelResult, OpenAICompatibleModelAdapter  # noqa: E402
from webapp import create_server  # noqa: E402

from test_m3_proposals import proposal_payload  # noqa: E402
from test_m4_full_text import FakeAdapter, candidate_payload, page_rewrite  # noqa: E402

# Loopback test requests must never go through a system/environment HTTP proxy
# (for example a local proxy at 127.0.0.1:1087 that rejects loopback targets).
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _open_direct(url_or_request):
    return _OPENER.open(url_or_request)


def seed_selected_proposal(db_path: Path, project_id: str = "project-m6") -> None:
    """Insert an established project with a SELECTED proposal on topic L2-T08."""
    now = datetime.now(timezone.utc).isoformat()
    proposal = {
        "proposal_index": 1, "title": "Ben Learns to Bounce",
        "entry_point_cn": "Ben在花园里学拍球。",
        "storyline": "Ben第一次拍球时总失败，朋友帮他找到节奏，最后成功。",
        "predicted_core_words": ["bounce a ball"],
        "predicted_core_patterns": ["How many?", "Good job!"],
        "predicted_extension_words": ["sticker"],
        "book_type": "TEXTBOOK_SYNC",
        "plot_structure": "失败—观察—练习—成功",
        "potential_issues": "", "creative_highlight": "",
    }
    with connect(db_path) as db:
        db.execute("""INSERT INTO proposal_batches
            (proposal_batch_id,topic_id,target_book_type,teacher_input_json,
             original_proposal_count,evaluation_json,selected_count,discarded_count,
             selection_finalized_at,created_at)
            VALUES ('batch-m6','L2-T08','ALL','{}',1,'{}',1,0,NULL,?)""", (now,))
        db.execute("""INSERT INTO projects
            (project_id,topic_id,working_title,status,selected_proposal_id,created_at,updated_at)
            VALUES (?,'L2-T08','Ben Learns to Bounce','ACTIVE','proposal-m6',?,?)""",
                   (project_id, now, now))
        db.execute("""INSERT INTO proposals
            (proposal_id,project_id,proposal_batch_id,proposal_index,payload_json,status,created_at,updated_at)
            VALUES ('proposal-m6',?, 'batch-m6',1,?,'SELECTED',?,?)""",
                   (project_id, json.dumps(proposal, ensure_ascii=False), now, now))


class M6WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.temp.name) / "m6.sqlite"
        build_database(cls.db, extract_all(DOCS_DIR))
        cls.project_id = "project-m6"
        seed_selected_proposal(cls.db, cls.project_id)
        settings = ModelSettings("fake", "", None, "fake-default", "fake-proposal",
                                 "fake-full", "fake-rewrite", 1)
        workflow = FullTextWorkflow(
            adapter=FakeAdapter([ModelResult(
                True, json.dumps(candidate_payload(2), ensure_ascii=False))]),
            database_path=cls.db, settings=settings)
        plan = workflow.prepare_generation_plan(cls.project_id, 8)
        workflow.confirm_generation_plan(plan["plan_id"])
        generated = workflow.generate_full_text_candidates(plan["plan_id"], 2)
        workflow.select_candidate_as_draft(generated["candidates"][0]["candidate_id"])

        cls.server = create_server(cls.db, port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()

    def get(self, path: str) -> tuple[int, bytes, str]:
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with _open_direct(url) as response:
                return response.status, response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers.get("Content-Type", "")

    def get_json(self, path: str) -> tuple[int, dict]:
        status, body, _ = self.get(path)
        return status, json.loads(body)

    def test_pages_are_served(self):
        for path in ("/", "/topic.html", "/project.html", "/library.html"):
            status, body, content_type = self.get(path)
            self.assertEqual(200, status, path)
            self.assertIn("text/html", content_type)
            self.assertIn(b"app.js", body)

    def test_topics_api_lists_topics_with_progress(self):
        status, data = self.get_json("/api/topics")
        self.assertEqual(200, status)
        self.assertEqual(9, len(data["topics"]))
        self.assertIn("system_vocabulary", data)
        topic = next(item for item in data["topics"] if item["topic_id"] == "L2-T08")
        self.assertIn("final_progress", topic)
        self.assertEqual(0, topic["final_progress"]["total_current_finals"])

    def test_topic_workspace_returns_basis_batches_and_projects(self):
        status, data = self.get_json("/api/topic?id=L2-T08")
        self.assertEqual(200, status)
        self.assertTrue(data["textbook_words"])
        self.assertTrue(data["textbook_structures"])
        self.assertEqual(1, len(data["batches"]))
        self.assertEqual("SELECTED", data["batches"][0]["proposals"][0]["status"])
        self.assertEqual(self.project_id, data["projects"][0]["project_id"])
        self.assertEqual("DRAFT", data["projects"][0]["stage"])

    def test_project_state_exposes_plan_draft_validation_and_gate(self):
        status, data = self.get_json(f"/api/project?id={self.project_id}")
        self.assertEqual(200, status)
        self.assertEqual("DRAFT", data["stage"])
        self.assertEqual("READY", data["plan"]["status"])
        self.assertTrue(data["plan"]["vocabulary"])
        self.assertEqual(2, len(data["candidates"]))
        self.assertEqual(8, len(data["draft"]["pages"]))
        self.assertIn("vocabulary_observations", data["draft"]["validation"])
        self.assertIsInstance(data["draft"]["validation_issues"], list)
        self.assertFalse(data["final_gate"]["ready"])

    def test_library_is_empty_before_any_final(self):
        status, data = self.get_json("/api/library")
        self.assertEqual(200, status)
        self.assertEqual([], data["books"])

    def test_unknown_resources_return_json_404(self):
        for path in ("/api/project?id=missing", "/api/topic?id=missing",
                     "/api/unknown", "/missing.html"):
            status, data = self.get_json(path)
            self.assertEqual(404, status, path)
            self.assertEqual("NOT_FOUND", data["error_code"])

    def test_static_paths_cannot_escape_static_dir(self):
        status, _, _ = self.get("/static/../backend/config.py")
        self.assertEqual(404, status)


class M6ProposalActionTests(unittest.TestCase):
    """POST endpoints delegate to ProposalWorkflow; model is a FakeAdapter."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "m6-actions.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.server = create_server(
            self.db, port=0,
            proposal_adapter=FakeAdapter([ModelResult(
                True, json.dumps(proposal_payload(), ensure_ascii=False))]))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _open_direct(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def get_json(self, path: str) -> dict:
        with _open_direct(f"http://127.0.0.1:{self.port}{path}") as response:
            return json.loads(response.read())

    def test_generate_establish_and_finalize_via_api(self):
        status, generated = self.post_json("/api/proposals/generate", {
            "topic_id": "L2-T08", "count": 8, "target_book_type": "ALL",
            "creative_instruction": "故事由行动体现坚持。"})
        self.assertEqual(200, status, generated)
        self.assertEqual(8, len(generated["proposals"]))
        batch_id = generated["proposal_batch_id"]

        workspace = self.get_json("/api/topic?id=L2-T08")
        self.assertEqual(batch_id, workspace["batches"][0]["proposal_batch_id"])
        proposal_ids = [item["proposal_id"]
                        for item in workspace["batches"][0]["proposals"][:2]]

        status, established = self.post_json("/api/batch/establish", {
            "proposal_batch_id": batch_id, "proposal_ids": proposal_ids})
        self.assertEqual(200, status, established)
        self.assertEqual(2, established["established_count"])

        status, finalized = self.post_json("/api/batch/finalize",
                                           {"proposal_batch_id": batch_id})
        self.assertEqual(200, status, finalized)
        self.assertEqual(2, finalized["selected_count"])
        self.assertEqual(6, finalized["discarded_count"])

        workspace = self.get_json("/api/topic?id=L2-T08")
        self.assertTrue(workspace["batches"][0]["selection_finalized_at"])
        self.assertEqual(2, len(workspace["batches"][0]["proposals"]))
        self.assertEqual(2, len(workspace["projects"]))
        self.assertEqual("PLAN", workspace["projects"][0]["stage"])

    def test_workflow_failures_surface_as_http_400_with_error_code(self):
        status, data = self.post_json("/api/batch/establish", {
            "proposal_batch_id": "missing-batch", "proposal_ids": ["p1"]})
        self.assertEqual(400, status)
        self.assertEqual("BATCH_NOT_FOUND", data["error_code"])
        status, data = self.post_json("/api/unknown-action", {})
        self.assertEqual(404, status)
        self.assertEqual("NOT_FOUND", data["error_code"])

    def test_manual_proposal_establishes_project_directly(self):
        status, created = self.post_json("/api/proposals/manual", {
            "topic_id": "L2-T08", "title": "The Broom Race",
            "book_type": "THEME_EXTENSION",
            "storyline": "大扫除时两人比赛扫地，先求快失败了，后来分工合作完成。",
            "entry_point_cn": "从大扫除分工切入。",
            "predicted_core_words": ["jump rope", "jump rope", " try "],
            "predicted_core_patterns": ["I'll try again."],
            "predicted_extension_words": []})
        self.assertEqual(200, status, created)
        project_id = created["project_id"]

        workspace = self.get_json("/api/topic?id=L2-T08")
        self.assertEqual([], workspace["batches"])  # internal manual batch stays hidden
        self.assertEqual(1, len(workspace["projects"]))
        self.assertEqual("The Broom Race", workspace["projects"][0]["working_title"])
        self.assertEqual("PLAN", workspace["projects"][0]["stage"])

        state = self.get_json(f"/api/project?id={project_id}")
        self.assertEqual("MANUAL", state["proposal"]["source"])
        self.assertEqual("THEME_EXTENSION", state["proposal"]["book_type"])

        status, plan = self.post_json("/api/plan/prepare",
                                      {"project_id": project_id, "page_count": 8})
        self.assertEqual(200, status, plan)
        core = [item["raw_form"] for item in plan["planned_vocabulary"]
                if item["role"] == "CORE"]
        self.assertEqual(["jump rope", "try"], core)

    def test_manual_proposal_frontend_body_with_blank_optionals(self):
        """Mirrors the exact body topic.html sends when optionals stay blank."""
        status, created = self.post_json("/api/proposals/manual", {
            "topic_id": "L2-T08", "title": "The Broom Race",
            "storyline": "大扫除时两人分工合作完成任务。",
            "book_type": "TEXTBOOK_SYNC",
            "entry_point_cn": "",
            "predicted_core_words": [],
            "predicted_core_patterns": [],
            "predicted_extension_words": []})
        self.assertEqual(200, status, created)

        state = self.get_json(f"/api/project?id={created['project_id']}")
        self.assertEqual("MANUAL", state["proposal"]["source"])
        self.assertEqual("", state["proposal"]["entry_point_cn"])

        status, plan = self.post_json("/api/plan/prepare", {
            "project_id": created["project_id"], "page_count": 8})
        self.assertEqual(200, status, plan)

        # Manual creation must never touch the model adapter: the single
        # queued FakeAdapter result must still be available for AI generation.
        status, generated = self.post_json("/api/proposals/generate",
                                           {"topic_id": "L2-T08"})
        self.assertEqual(200, status, generated)

    def test_manual_proposal_language_recommendation_flows_into_plan(self):
        """Manual story -> AI language suggestions -> normal Plan confirmation."""
        self.server.shutdown()
        self.server.server_close()
        self.server = create_server(
            self.db, port=0,
            proposal_adapter=FakeAdapter([ModelResult(True, json.dumps({
                "predicted_core_words": ["clean", "help"],
                "predicted_extension_words": ["broom"],
                "predicted_core_patterns": ["Let me help you."],
            }, ensure_ascii=False))]))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        status, created = self.post_json("/api/proposals/manual", {
            "topic_id": "L2-T08", "title": "The Helping Broom",
            "book_type": "TEXTBOOK_SYNC",
            "storyline": "Amy 想打扫教室，扫帚太大，同伴轮流帮忙一起完成。",
            "entry_point_cn": "", "predicted_core_words": [],
            "predicted_core_patterns": [], "predicted_extension_words": []})
        self.assertEqual(200, status, created)

        status, recommended = self.post_json("/api/proposals/recommend-language",
                                             {"proposal_id": created["proposal_id"]})
        self.assertEqual(200, status, recommended)
        self.assertEqual(["clean", "help"], recommended["predicted_core_words"])

        # Suggestions persist on the Proposal and survive a page refresh.
        state = self.get_json(f"/api/project?id={created['project_id']}")
        self.assertEqual(["clean", "help"], state["proposal"]["predicted_core_words"])
        self.assertEqual("MANUAL", state["proposal"]["source"])

        # The normal Plan lifecycle picks the suggestions up; teacher confirms.
        status, plan = self.post_json("/api/plan/prepare", {
            "project_id": created["project_id"], "page_count": 8})
        self.assertEqual(200, status, plan)
        roles = {item["raw_form"]: item["role"] for item in plan["planned_vocabulary"]}
        self.assertEqual("CORE", roles.get("clean"))
        self.assertEqual("CORE", roles.get("help"))
        self.assertEqual("EXTENSION", roles.get("broom"))
        self.assertIn("Let me help you.",
                      [item["raw_pattern"] for item in plan["planned_core_patterns"]])
        status, confirmed = self.post_json("/api/plan/confirm",
                                           {"plan_id": plan["plan_id"]})
        self.assertEqual(200, status, confirmed)
        self.assertEqual("READY", confirmed["status"])

    def test_manual_proposal_requires_fields_and_concrete_type(self):
        status, data = self.post_json("/api/proposals/manual", {
            "topic_id": "L2-T08", "title": "X", "book_type": "ALL", "storyline": "y"})
        self.assertEqual(400, status)
        self.assertEqual("INVALID_BOOK_TYPE", data["error_code"])
        status, data = self.post_json("/api/proposals/manual", {
            "topic_id": "L2-T08", "title": " ", "book_type": "TEXTBOOK_SYNC",
            "storyline": ""})
        self.assertEqual(400, status)
        self.assertEqual("MANUAL_FIELDS_REQUIRED", data["error_code"])


class M6PlanCandidateActionTests(unittest.TestCase):
    """Segment 2 POST endpoints: language plan and full-text candidates."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "m6-plan.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.project_id = "project-m6"
        seed_selected_proposal(self.db, self.project_id)
        self.server = create_server(
            self.db, port=0,
            full_text_adapter=FakeAdapter([ModelResult(
                True, json.dumps(candidate_payload(2), ensure_ascii=False))]))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _open_direct(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def get_json(self, path: str) -> dict:
        with _open_direct(f"http://127.0.0.1:{self.port}{path}") as response:
            return json.loads(response.read())

    def test_plan_adjust_confirm_generate_and_select_via_api(self):
        status, plan = self.post_json("/api/plan/prepare", {
            "project_id": self.project_id, "page_count": 8,
            "generation_orientation": "BALANCED", "teacher_instruction": "句子短一些。"})
        self.assertEqual(200, status, plan)
        self.assertEqual("DRAFT", plan["status"])
        core = [item["raw_form"] for item in plan["planned_vocabulary"]
                if item["role"] == "CORE"]
        self.assertIn("bounce a ball", core)

        status, adjusted = self.post_json("/api/plan/prepare", {
            "project_id": self.project_id, "page_count": 8,
            "planned_extension_words": ["sticker", "checkpoint"]})
        self.assertEqual(200, status, adjusted)
        self.assertNotEqual(plan["plan_id"], adjusted["plan_id"])
        extension = {item["raw_form"]: item["source_lookup_status"]
                     for item in adjusted["planned_vocabulary"]
                     if item["role"] == "EXTENSION"}
        self.assertEqual({"sticker", "checkpoint"}, set(extension))
        self.assertEqual("UNRESOLVED", extension["checkpoint"])

        status, confirmed = self.post_json("/api/plan/confirm",
                                           {"plan_id": adjusted["plan_id"]})
        self.assertEqual(200, status, confirmed)
        self.assertEqual("READY", confirmed["status"])
        state = self.get_json(f"/api/project?id={self.project_id}")
        self.assertEqual("PLAN_READY", state["stage"])

        status, generated = self.post_json("/api/candidates/generate", {
            "plan_id": adjusted["plan_id"], "candidate_count": 2})
        self.assertEqual(200, status, generated)
        self.assertEqual(2, generated["candidate_count"])
        state = self.get_json(f"/api/project?id={self.project_id}")
        self.assertEqual("CANDIDATES", state["stage"])
        self.assertEqual(2, len(state["candidates"]))

        candidate_id = generated["candidates"][0]["candidate_id"]
        status, selected = self.post_json("/api/candidate/select",
                                          {"candidate_id": candidate_id})
        self.assertEqual(200, status, selected)
        state = self.get_json(f"/api/project?id={self.project_id}")
        self.assertEqual("DRAFT", state["stage"])
        self.assertEqual(8, len(state["draft"]["pages"]))
        self.assertEqual("SELECTED", next(
            item["status"] for item in state["candidates"]
            if item["candidate_id"] == candidate_id))

    def test_plan_and_candidate_failures_surface_as_http_400(self):
        status, data = self.post_json("/api/plan/prepare",
                                      {"project_id": self.project_id, "page_count": 9})
        self.assertEqual(400, status)
        self.assertEqual("INVALID_PAGE_COUNT", data["error_code"])

        status, plan = self.post_json("/api/plan/prepare",
                                      {"project_id": self.project_id, "page_count": 8})
        self.assertEqual(200, status)
        status, data = self.post_json("/api/candidates/generate",
                                      {"plan_id": plan["plan_id"], "candidate_count": 2})
        self.assertEqual(400, status)
        self.assertEqual("PLAN_NOT_READY", data["error_code"])

        status, data = self.post_json("/api/candidate/select",
                                      {"candidate_id": "missing-candidate"})
        self.assertEqual(400, status)
        self.assertEqual("CANDIDATE_NOT_FOUND", data["error_code"])

    def test_provider_http_404_is_never_a_route_404(self):
        """M7 E2E bug: a provider-side 404 (wrong API URL / model name) must
        surface as PROVIDER_ERROR with diagnosable detail, while the
        /api/candidates/generate route itself keeps answering."""
        status, plan = self.post_json("/api/plan/prepare",
                                      {"project_id": self.project_id, "page_count": 8})
        self.assertEqual(200, status, plan)
        status, confirmed = self.post_json("/api/plan/confirm",
                                           {"plan_id": plan["plan_id"]})
        self.assertEqual(200, status, confirmed)

        self.server.shutdown()
        self.server.server_close()
        provider_message = ("Provider returned HTTP 404 (model 'doubao-x', endpoint "
                            "https://provider.example/api/wrong/chat/completions)")
        self.server = create_server(
            self.db, port=0,
            full_text_adapter=FakeAdapter([ModelResult(
                False, error_code="PROVIDER_ERROR",
                error_message=provider_message)]))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        status, data = self.post_json("/api/candidates/generate", {
            "plan_id": plan["plan_id"], "candidate_count": 2})
        self.assertEqual(400, status, data)  # a route 404 would fail here
        self.assertEqual("PROVIDER_ERROR", data["error_code"])
        self.assertIn("HTTP 404", data["message"])
        self.assertIn("doubao-x", data["message"])


class M6DraftActionTests(unittest.TestCase):
    """Draft-stage endpoints: autosave, vocabulary, issues, rewrite, finalize."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "m6-draft.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.project_id = "project-m6"
        seed_selected_proposal(self.db, self.project_id)
        settings = ModelSettings("fake", "", None, "fake-default", "fake-proposal",
                                 "fake-full", "fake-rewrite", 1)
        workflow = FullTextWorkflow(
            adapter=FakeAdapter([ModelResult(
                True, json.dumps(candidate_payload(2), ensure_ascii=False))]),
            database_path=self.db, settings=settings)
        plan = workflow.prepare_generation_plan(self.project_id, 8)
        workflow.confirm_generation_plan(plan["plan_id"])
        generated = workflow.generate_full_text_candidates(plan["plan_id"], 2)
        workflow.select_candidate_as_draft(generated["candidates"][0]["candidate_id"])

        rewrite_one = page_rewrite(
            "Ben taps the ball near the gate. He counts one and two.")
        rewrite_two = page_rewrite("Ben holds the ball and smiles at Mia.")
        self.server = create_server(
            self.db, port=0,
            full_text_adapter=FakeAdapter([
                ModelResult(True, json.dumps(rewrite_one, ensure_ascii=False)),
                ModelResult(True, json.dumps(rewrite_two, ensure_ascii=False))]))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _open_direct(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def get_json(self, path: str) -> dict:
        with _open_direct(f"http://127.0.0.1:{self.port}{path}") as response:
            return json.loads(response.read())

    def state(self) -> dict:
        return self.get_json(f"/api/project?id={self.project_id}")

    def test_draft_to_final_flow_via_api(self):
        state = self.state()
        draft_id = state["draft"]["draft_id"]

        # 1) Autosave an edited page; validation reruns on the new content.
        pages = state["draft"]["pages"]
        pages[1]["text"] = "The ball rolls away from Ben. He walks and brings it back."
        status, saved = self.post_json("/api/draft/autosave",
                                       {"draft_id": draft_id, "pages": pages})
        self.assertEqual(200, status, saved)
        state = self.state()
        self.assertIn("rolls away from Ben", state["draft"]["pages"][1]["text"])

        # 2) Rewrite preview: create, surface on refresh, cancel, recreate, accept.
        status, preview = self.post_json("/api/rewrite/preview", {
            "draft_id": draft_id, "scope": "PAGE", "page_number": 1,
            "teacher_instruction": "第一页更安静一些。"})
        self.assertEqual(200, status, preview)
        state = self.state()
        self.assertEqual(preview["rewrite_preview_id"],
                         state["rewrite_preview"]["rewrite_preview_id"])
        status, cancelled = self.post_json("/api/rewrite/cancel", {
            "rewrite_preview_id": preview["rewrite_preview_id"]})
        self.assertEqual(200, status, cancelled)
        self.assertTrue(cancelled["draft_unchanged"])
        state = self.state()
        self.assertIsNone(state["rewrite_preview"])
        status, preview = self.post_json("/api/rewrite/preview", {
            "draft_id": draft_id, "scope": "PAGE", "page_number": 1,
            "teacher_instruction": "第一页更温和。"})
        self.assertEqual(200, status, preview)
        status, accepted = self.post_json("/api/rewrite/accept", {
            "rewrite_preview_id": preview["rewrite_preview_id"]})
        self.assertEqual(200, status, accepted)
        state = self.state()
        self.assertEqual("Ben holds the ball and smiles at Mia.",
                         state["draft"]["pages"][0]["text"])

        # 3) Promote one NEEDS_REVIEW word into the plan, then confirm the revision.
        review = [item for item in
                  state["draft"]["validation"]["vocabulary_observations"]
                  if item["classification_state"] == "NEEDS_REVIEW"]
        self.assertTrue(review)
        promoted = review[0]
        status, revised = self.post_json("/api/plan/revise", {
            "draft_id": draft_id,
            "selections": [{"normalized_form": promoted["normalized_form"],
                            "role": "EXTENSION"}]})
        self.assertEqual(200, status, revised)
        self.assertEqual("DRAFT", revised["status"])
        status, confirmed = self.post_json("/api/plan/confirm",
                                           {"plan_id": revised["plan_id"]})
        self.assertEqual(200, status, confirmed)
        state = self.state()
        promoted_now = next(
            item for item in state["draft"]["validation"]["vocabulary_observations"]
            if item["normalized_form"] == promoted["normalized_form"])
        self.assertEqual("PLANNED", promoted_now["classification_state"])

        # 4) Confirm every remaining NEEDS_REVIEW word as non-teaching context.
        remaining = [item for item in
                     state["draft"]["validation"]["vocabulary_observations"]
                     if item["classification_state"] == "NEEDS_REVIEW"]
        entries = [{
            "raw_form": item["raw_form"], "normalized_form": item["normalized_form"],
            "lemma": item["lemma"], "source_status": item["source_lookup_status"],
            "classification_state": "NEEDS_REVIEW",
            "confirmed_role": "NON_TEACHING_CONTEXT", "teacher_confirmed": True,
        } for item in remaining]
        status, confirmation = self.post_json("/api/vocabulary/confirm", {
            "draft_id": draft_id, "snapshot": {"entries": entries}})
        self.assertEqual(200, status, confirmation)
        self.assertTrue(confirmation["ready_for_final"])
        state = self.state()
        self.assertEqual(
            0, state["draft"]["validation"]["metrics"]["needs_review_unconfirmed_count"])

        # 5) Acknowledge every open warning on the latest validation run.
        for issue in state["draft"]["validation_issues"]:
            if issue["severity"] == "WARNING" and issue["resolution_status"] == "OPEN":
                status, acked = self.post_json("/api/issue/acknowledge",
                                               {"issue_id": issue["issue_id"]})
                self.assertEqual(200, status, acked)

        # 6) Gate turns ready; finalize through the API.
        state = self.state()
        self.assertTrue(state["final_gate"]["ready"], state["final_gate"])
        status, final = self.post_json("/api/final/finalize",
                                       {"project_id": self.project_id})
        self.assertEqual(200, status, final)
        state = self.state()
        self.assertEqual("FINAL", state["stage"])
        self.assertEqual(final["book_id"], state["final_book"]["book_id"])
        library = self.get_json("/api/library")
        self.assertEqual(1, len(library["books"]))
        book = self.get_json(f"/api/book?id={final['book_id']}")
        self.assertEqual(8, len(book["snapshot"]["pages"]))

    def test_missing_credentials_use_dedicated_error_code(self):
        """UI maps MODEL_NOT_CONFIGURED to the friendly Chinese hint; keep the code stable."""
        adapter = OpenAICompatibleModelAdapter(
            ModelSettings("openai_compatible", "", None, "m", "m", "m", "m", 1))
        result = adapter.generate("PROPOSAL", [], {}, {})
        self.assertFalse(result.ok)
        self.assertEqual("MODEL_NOT_CONFIGURED", result.error_code)

    def test_finalize_rejected_while_gate_blocked(self):
        status, data = self.post_json("/api/final/finalize",
                                      {"project_id": self.project_id})
        self.assertEqual(400, status)
        self.assertEqual("FINAL_GATE_BLOCKED", data["error_code"])
        status, data = self.post_json("/api/fact-review", {
            "draft_id": self.state()["draft"]["draft_id"],
            "status": "VERIFIED_BY_USER"})
        self.assertEqual(400, status)
        self.assertEqual("VERIFICATION_NOTE_REQUIRED", data["error_code"])


if __name__ == "__main__":
    unittest.main()
