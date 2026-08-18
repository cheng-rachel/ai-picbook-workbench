"""Provider-neutral model boundary with one optional OpenAI-compatible HTTP adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import socket
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ModelSettings


@dataclass(frozen=True)
class ModelResult:
    ok: bool
    text: str = ""
    error_code: str | None = None
    error_message: str | None = None
    provider_metadata: dict[str, Any] | None = None


class ModelAdapter(Protocol):
    def generate(self, task_type: str, messages: list[dict], output_schema: dict,
                 model_config: dict) -> ModelResult: ...


def normalize_chat_completions_url(api_url: str) -> str:
    """Accept both a full chat-completions endpoint and a bare base URL.

    OpenAI-compatible providers document their endpoint as `<base>/chat/completions`
    but consoles usually show only `<base>` (e.g. `.../api/v3`), so teachers often
    paste the base URL into the model settings page. Appending the standard path
    keeps both forms working.
    """
    url = api_url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


class OpenAICompatibleModelAdapter:
    """Minimal JSON HTTP adapter; all provider details stay behind ModelAdapter."""

    def __init__(self, settings: ModelSettings | None = None):
        self.settings = settings or ModelSettings.from_environment()

    def generate(self, task_type: str, messages: list[dict], output_schema: dict,
                 model_config: dict) -> ModelResult:
        if not self.settings.api_key or not self.settings.api_url:
            # Distinct code so the UI can show a friendly "not configured" hint;
            # the raw message stays as-is for developer diagnostics.
            return ModelResult(False, error_code="MODEL_NOT_CONFIGURED",
                               error_message="MODEL_API_KEY or MODEL_API_URL is not configured")
        model = model_config.get("model") or self.settings.model_for(task_type)
        api_url = normalize_chat_completions_url(self.settings.api_url)
        body_payload = {"model": model, "messages": messages,
                        "response_format": {"type": "json_object"}}
        if "temperature" in model_config:
            body_payload["temperature"] = model_config["temperature"]
        body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
        request = Request(api_url, data=body, method="POST",
                          headers={"Authorization": f"Bearer {self.settings.api_key}",
                                   "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                return ModelResult(False, error_code="EMPTY_OUTPUT", error_message="Provider returned empty content")
            return ModelResult(True, text=text, provider_metadata={"model": payload.get("model", model)})
        except (TimeoutError, socket.timeout) as exc:
            return ModelResult(False, error_code="TIMEOUT", error_message=str(exc))
        except HTTPError as exc:
            # A provider-side 404/401/... must stay distinguishable from our own
            # web routes; include the endpoint, model, and response excerpt so a
            # wrong URL or model name is diagnosable from the UI toast alone.
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()[:200]
            except OSError:
                pass
            return ModelResult(
                False, error_code="PROVIDER_ERROR",
                error_message=f"Provider returned HTTP {exc.code} "
                              f"(model '{model}', endpoint {api_url})"
                              + (f": {detail}" if detail else ""))
        except (URLError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return ModelResult(False, error_code="PROVIDER_ERROR", error_message=str(exc))
