"""M7 in-app model configuration: .env.local storage, priority, live effect."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "05app"))
sys.path.insert(0, str(ROOT / "06tests"))

from backend.config import ModelSettings, load_local_env  # noqa: E402
from backend.database import build_database  # noqa: E402
from backend.extractors import extract_all  # noqa: E402
from backend.config import DOCS_DIR  # noqa: E402
from backend.model_adapter import (OpenAICompatibleModelAdapter,  # noqa: E402
                                   normalize_chat_completions_url)
from backend.model_config import read_model_config, save_model_config  # noqa: E402
from webapp import create_server  # noqa: E402

from test_m3_proposals import proposal_payload  # noqa: E402

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

MODEL_ENV_KEYS = ("MODEL_PROVIDER", "MODEL_API_URL", "MODEL_API_KEY", "DEFAULT_MODEL",
                  "PROPOSAL_MODEL", "FULL_TEXT_MODEL", "REWRITE_MODEL",
                  "MODEL_TIMEOUT_SECONDS")


class EnvIsolationMixin:
    """Point .env.local at a temp file and clear shell model variables."""

    def isolate_environment(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env_local = Path(self.temp.name) / ".env.local"
        self.saved_env = {key: os.environ.pop(key, None)
                          for key in MODEL_ENV_KEYS + ("PICBOOK_ENV_LOCAL",
                                                       "no_proxy", "NO_PROXY")}
        os.environ["PICBOOK_ENV_LOCAL"] = str(self.env_local)
        # The in-process model adapter must reach the loopback fake provider
        # directly even when a system-wide HTTP proxy is configured.
        os.environ["no_proxy"] = "127.0.0.1,localhost"
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    def restore_environment(self):
        for key in ("PICBOOK_ENV_LOCAL",):
            os.environ.pop(key, None)
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()


class ModelConfigStorageTests(EnvIsolationMixin, unittest.TestCase):
    def setUp(self):
        self.isolate_environment()

    def tearDown(self):
        self.restore_environment()

    def test_priority_shell_env_over_env_local_over_default(self):
        settings = ModelSettings.from_environment()
        self.assertIsNone(settings.api_key)
        self.assertEqual("default", settings.default_model)

        saved = save_model_config({
            "model_provider": "openai_compatible", "model_api_url": "https://file.example/v1",
            "model_api_key": "file-key-12345678", "default_model": "file-model"})
        self.assertTrue(saved["ok"], saved)
        settings = ModelSettings.from_environment()
        self.assertEqual("https://file.example/v1", settings.api_url)
        self.assertEqual("file-key-12345678", settings.api_key)
        self.assertEqual("file-model", settings.model_for("FULL_TEXT"))

        os.environ["MODEL_API_URL"] = "https://shell.example/v1"
        settings = ModelSettings.from_environment()
        self.assertEqual("https://shell.example/v1", settings.api_url)
        self.assertEqual("file-key-12345678", settings.api_key)

    def test_save_validates_required_and_keeps_stored_key_when_blank(self):
        missing = save_model_config({"model_provider": "openai_compatible"})
        self.assertFalse(missing["ok"])
        self.assertEqual("CONFIG_FIELDS_REQUIRED", missing["error_code"])
        self.assertFalse(self.env_local.exists())

        save_model_config({
            "model_provider": "openai_compatible", "model_api_url": "https://a.example",
            "model_api_key": "secret-key-12345678", "default_model": "m1"})
        mode = stat.S_IMODE(self.env_local.stat().st_mode)
        self.assertEqual(0o600, mode)

        # Editing without retyping the key keeps the stored secret.
        updated = save_model_config({
            "model_provider": "openai_compatible", "model_api_url": "https://a.example",
            "model_api_key": "", "default_model": "m2", "proposal_model": "story-m"})
        self.assertTrue(updated["ok"], updated)
        stored = load_local_env(self.env_local)
        self.assertEqual("secret-key-12345678", stored["MODEL_API_KEY"])
        self.assertEqual("m2", stored["DEFAULT_MODEL"])

        settings = ModelSettings.from_environment()
        self.assertEqual("story-m", settings.model_for("PROPOSAL"))
        self.assertEqual("m2", settings.model_for("FULL_TEXT"))  # blank -> default

    def test_read_never_exposes_full_key(self):
        save_model_config({
            "model_provider": "openai_compatible", "model_api_url": "https://a.example",
            "model_api_key": "secret-key-12345678", "default_model": "m1"})
        view = json.dumps(read_model_config(), ensure_ascii=False)
        self.assertNotIn("secret-key-12345678", view)
        data = read_model_config()
        self.assertTrue(data["configured"])
        self.assertTrue(data["api_key_set"])
        self.assertEqual("…5678", data["api_key_hint"])


def _start_fake_provider(requests_log: list) -> ThreadingHTTPServer:
    class FakeProvider(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length))
            requests_log.append({"model": payload.get("model"),
                                 "authorization": self.headers.get("Authorization"),
                                 "path": self.path})
            content = json.dumps(proposal_payload(), ensure_ascii=False)
            body = json.dumps({"model": payload.get("model"),
                               "choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class ModelConfigLiveEffectTests(EnvIsolationMixin, unittest.TestCase):
    """End to end: save config in the app, real adapter calls the configured URL."""

    def setUp(self):
        self.isolate_environment()
        self.db = Path(self.temp.name) / "m7.sqlite"
        build_database(self.db, extract_all(DOCS_DIR))
        self.provider_requests: list = []
        self.provider = _start_fake_provider(self.provider_requests)
        self.provider_url = f"http://127.0.0.1:{self.provider.server_address[1]}/v1/chat"
        self.server = create_server(self.db, port=0)  # no injected adapter: real one
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.provider.shutdown()
        self.provider.server_close()
        self.restore_environment()

    def post_json(self, path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with _OPENER.open(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def get_json(self, path: str) -> dict:
        with _OPENER.open(f"http://127.0.0.1:{self.port}{path}") as response:
            return json.loads(response.read())

    def restart_app_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.server = create_server(self.db, port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def test_configure_use_restart_and_switch_task_model(self):
        # 1) Fresh state: browsable, AI blocked with the dedicated error code.
        self.assertFalse(self.get_json("/api/model-config")["configured"])
        self.assertEqual(9, len(self.get_json("/api/topics")["topics"]))
        status, blocked = self.post_json("/api/proposals/generate",
                                         {"topic_id": "L2-T08"})
        self.assertEqual(400, status)
        self.assertEqual("MODEL_NOT_CONFIGURED", blocked["error_code"])

        # 2) Save config in the app; generation immediately uses it.
        status, saved = self.post_json("/api/model-config", {
            "model_provider": "openai_compatible", "model_api_url": self.provider_url,
            "model_api_key": "live-key-12345678", "default_model": "base-model"})
        self.assertEqual(200, status, saved)
        status, generated = self.post_json("/api/proposals/generate",
                                           {"topic_id": "L2-T08"})
        self.assertEqual(200, status, generated)
        self.assertEqual(8, len(generated["proposals"]))
        self.assertEqual("base-model", self.provider_requests[-1]["model"])
        self.assertEqual("Bearer live-key-12345678",
                         self.provider_requests[-1]["authorization"])

        # 3) "Relaunch": a fresh server picks the stored config up automatically.
        self.restart_app_server()
        config = self.get_json("/api/model-config")
        self.assertTrue(config["configured"])
        self.assertNotIn("live-key-12345678", json.dumps(config))
        status, generated = self.post_json("/api/proposals/generate",
                                           {"topic_id": "L2-T08"})
        self.assertEqual(200, status, generated)

        # 4) Switch the proposal task model (blank key keeps the stored one).
        status, saved = self.post_json("/api/model-config", {
            "model_provider": "openai_compatible", "model_api_url": self.provider_url,
            "model_api_key": "", "default_model": "base-model",
            "proposal_model": "story-model"})
        self.assertEqual(200, status, saved)
        status, generated = self.post_json("/api/proposals/generate",
                                           {"topic_id": "L2-T08"})
        self.assertEqual(200, status, generated)
        self.assertEqual("story-model", self.provider_requests[-1]["model"])
        self.assertEqual("Bearer live-key-12345678",
                         self.provider_requests[-1]["authorization"])


class ModelAdapterEndpointTests(EnvIsolationMixin, unittest.TestCase):
    """M7 E2E bug fix: base-URL configs work; provider errors stay diagnosable.

    A provider-side HTTP 404 (wrong URL path or model name) must never read
    like a missing web route; the message names the endpoint and model.
    """

    def setUp(self):
        self.isolate_environment()

    def tearDown(self):
        self.restore_environment()

    def _settings(self, api_url: str, model: str = "test-model") -> ModelSettings:
        return ModelSettings("openai_compatible", api_url, "adapter-key",
                             model, model, model, model, 5)

    def test_normalize_accepts_full_endpoint_and_bare_base_url(self):
        full = "https://ark.example/api/v3/chat/completions"
        self.assertEqual(full, normalize_chat_completions_url(full))
        self.assertEqual(full, normalize_chat_completions_url("https://ark.example/api/v3"))
        self.assertEqual(full, normalize_chat_completions_url("https://ark.example/api/v3/"))

    def test_adapter_appends_chat_completions_to_base_url(self):
        requests_log: list = []
        provider = _start_fake_provider(requests_log)
        try:
            base_url = f"http://127.0.0.1:{provider.server_address[1]}/api/v3"
            adapter = OpenAICompatibleModelAdapter(self._settings(base_url))
            result = adapter.generate(
                "FULL_TEXT", [{"role": "user", "content": "hi"}], {}, {})
            self.assertTrue(result.ok, result.error_message)
            self.assertEqual("/api/v3/chat/completions", requests_log[-1]["path"])
        finally:
            provider.shutdown()
            provider.server_close()

    def test_provider_http_error_reports_endpoint_model_and_body(self):
        error_body = json.dumps({"error": "404 page not found"}).encode()

        class NotFoundProvider(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body)

        provider = ThreadingHTTPServer(("127.0.0.1", 0), NotFoundProvider)
        threading.Thread(target=provider.serve_forever, daemon=True).start()
        try:
            wrong_url = (f"http://127.0.0.1:{provider.server_address[1]}"
                         "/api/wrong-path/chat/completions")
            adapter = OpenAICompatibleModelAdapter(
                self._settings(wrong_url, model="doubao-test"))
            result = adapter.generate(
                "FULL_TEXT", [{"role": "user", "content": "hi"}], {}, {})
            self.assertFalse(result.ok)
            self.assertEqual("PROVIDER_ERROR", result.error_code)
            self.assertIn("HTTP 404", result.error_message)
            self.assertIn("doubao-test", result.error_message)
            self.assertIn("/api/wrong-path/chat/completions", result.error_message)
            self.assertIn("404 page not found", result.error_message)
            self.assertNotIn("adapter-key", result.error_message)
        finally:
            provider.shutdown()
            provider.server_close()


if __name__ == "__main__":
    unittest.main()
