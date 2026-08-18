"""Zero-dependency local web server for the teacher Demo UI.

Routing is a flat table lookup; anything needing real routing, sessions, or
state management belongs to a future production stack, not here.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.config import DATABASE_PATH
from backend.finalization_workflow import FinalizationWorkflow
from backend.full_text_workflow import FullTextWorkflow
from backend.model_config import read_model_config, save_model_config
from backend.proposal_workflow import ProposalWorkflow

from . import queries

STATIC_DIR = Path(__file__).resolve().parent / "static"
PAGES = {"/": "index.html", "/index.html": "index.html", "/topic.html": "topic.html",
         "/project.html": "project.html", "/library.html": "library.html",
         "/settings.html": "settings.html"}
CONTENT_TYPES = {".html": "text/html; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".js": "text/javascript; charset=utf-8"}


def create_server(database_path: Path = DATABASE_PATH, port: int = 8765,
                  proposal_adapter=None, full_text_adapter=None) -> ThreadingHTTPServer:
    """Adapters are injectable so tests can run the API without a real model."""
    database_path = Path(database_path)

    class ForgeHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002 - quiet by default
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            try:
                if parsed.path.startswith("/api/"):
                    self._api(parsed.path, params)
                else:
                    self._static(parsed.path)
            except Exception as exc:  # surface as JSON, never a stack trace page
                self._json({"ok": False, "error_code": "SERVER_ERROR",
                            "message": str(exc)}, status=500)

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                result = self._post_action(parsed.path, body)
                if result is None:
                    return self._not_found("Unknown API action")
                self._json(result, status=200 if result.get("ok") else 400)
            except Exception as exc:
                self._json({"ok": False, "error_code": "SERVER_ERROR",
                            "message": str(exc)}, status=500)

        def _post_action(self, path: str, body: dict) -> dict | None:
            """Each action delegates 1:1 to a backend workflow method."""
            if path == "/api/model-config":
                return save_model_config(body)
            if path == "/api/proposals/generate":
                teacher_input = {}
                if body.get("creative_instruction", "").strip():
                    teacher_input["creative_instruction"] = body["creative_instruction"].strip()
                return ProposalWorkflow(
                    adapter=proposal_adapter, database_path=database_path,
                ).generate_proposals(
                    body.get("topic_id", ""), int(body.get("count", 8)),
                    teacher_input, body.get("target_book_type", "ALL"))
            if path == "/api/proposals/manual":
                return ProposalWorkflow(
                    adapter=proposal_adapter, database_path=database_path,
                ).create_manual_proposal(body.get("topic_id", ""), body)
            if path == "/api/proposals/recommend-language":
                return ProposalWorkflow(
                    adapter=proposal_adapter, database_path=database_path,
                ).recommend_language_for_proposal(body.get("proposal_id", ""))
            if path == "/api/batch/establish":
                return ProposalWorkflow(
                    adapter=proposal_adapter, database_path=database_path,
                ).establish_projects_from_proposals(
                    body.get("proposal_batch_id", ""), body.get("proposal_ids", []))
            if path == "/api/batch/finalize":
                return ProposalWorkflow(
                    adapter=proposal_adapter, database_path=database_path,
                ).finalize_proposal_batch_selection(body.get("proposal_batch_id", ""))
            full_text = lambda: FullTextWorkflow(  # noqa: E731 - one-line factory
                adapter=full_text_adapter, database_path=database_path)
            if path == "/api/plan/prepare":
                return full_text().prepare_generation_plan(
                    body.get("project_id", ""), int(body.get("page_count", 8)),
                    body.get("generation_orientation", "BALANCED"),
                    body.get("teacher_instruction", "").strip(),
                    body.get("planned_core_words"),
                    body.get("planned_extension_words"),
                    body.get("planned_review_words"),
                    body.get("planned_core_patterns"))
            if path == "/api/plan/confirm":
                return full_text().confirm_generation_plan(body.get("plan_id", ""))
            if path == "/api/candidates/generate":
                return full_text().generate_full_text_candidates(
                    body.get("plan_id", ""), int(body.get("candidate_count", 3)))
            if path == "/api/candidate/select":
                return full_text().select_candidate_as_draft(body.get("candidate_id", ""))
            if path == "/api/draft/autosave":
                return full_text().autosave_draft(
                    body.get("draft_id", ""), body.get("pages") or [])
            if path == "/api/vocabulary/confirm":
                return full_text().confirm_vocabulary(
                    body.get("draft_id", ""), body.get("snapshot") or {})
            if path == "/api/plan/revise":
                return full_text().revise_generation_plan_from_vocabulary(
                    body.get("draft_id", ""), body.get("selections") or [])
            if path == "/api/issue/acknowledge":
                return full_text().acknowledge_validation_issue(
                    body.get("issue_id", ""), body.get("note") or None)
            if path == "/api/fact-review":
                return full_text().update_fact_review(
                    body.get("draft_id", ""), body.get("status", ""), body.get("note"))
            if path == "/api/rewrite/preview":
                return full_text().create_rewrite_preview(
                    body.get("draft_id", ""), body.get("scope", "FULL"),
                    body.get("teacher_instruction", ""), body.get("page_number"))
            if path == "/api/rewrite/accept":
                return full_text().accept_rewrite_preview(
                    body.get("rewrite_preview_id", ""))
            if path == "/api/rewrite/cancel":
                return full_text().cancel_rewrite_preview(
                    body.get("rewrite_preview_id", ""))
            if path == "/api/final/finalize":
                return FinalizationWorkflow(database_path=database_path).finalize_book(
                    body.get("project_id", ""))
            if path == "/api/final/unfinalize":
                return FinalizationWorkflow(database_path=database_path).unfinalize_book(
                    body.get("book_id", ""))
            return None

        def _api(self, path: str, params: dict) -> None:
            if path == "/api/model-config":
                return self._json(read_model_config())
            if path == "/api/topics":
                return self._json(queries.list_topics(database_path))
            if path == "/api/topic":
                data = queries.topic_workspace(database_path, params.get("id", ""))
                return self._json(data) if data else self._not_found("Topic not found")
            if path == "/api/project":
                data = queries.project_state(database_path, params.get("id", ""))
                return self._json(data) if data else self._not_found("Project not found")
            if path == "/api/library":
                return self._json(queries.library(database_path))
            if path == "/api/book":
                data = queries.book_detail(database_path, params.get("id", ""))
                return self._json(data) if data else self._not_found("Book not found")
            return self._not_found("Unknown API path")

        def _static(self, path: str) -> None:
            name = PAGES.get(path)
            if name is None and path.startswith("/static/"):
                candidate = path[len("/static/"):]
                if "/" not in candidate and (STATIC_DIR / candidate).is_file():
                    name = candidate
            if name is None:
                return self._not_found("Page not found")
            payload = (STATIC_DIR / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             CONTENT_TYPES.get(Path(name).suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, data: dict, status: int = 200) -> None:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _not_found(self, message: str) -> None:
            self._json({"ok": False, "error_code": "NOT_FOUND", "message": message},
                       status=404)

    return ThreadingHTTPServer(("127.0.0.1", port), ForgeHandler)
