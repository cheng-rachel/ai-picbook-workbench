from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "01docs"


def env_local_path() -> Path:
    """Model config file; PICBOOK_ENV_LOCAL overrides it (used by tests)."""
    return Path(os.environ.get("PICBOOK_ENV_LOCAL") or PROJECT_ROOT / ".env.local")


def load_local_env(path: Path | None = None) -> dict:
    """Parse KEY=VALUE lines from .env.local; missing file means empty config."""
    path = path or env_local_path()
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values
STRUCTURED_DIR = PROJECT_ROOT / "02data" / "structured"
DATABASE_PATH = STRUCTURED_DIR / "picbook_forge.sqlite"
RAG_DIR = PROJECT_ROOT / "03rag"
RAG_PROCESSED_DIR = RAG_DIR / "processed"
RAG_INDEX_DIR = RAG_DIR / "index"
RAG_INDEX_PATH = RAG_INDEX_DIR / "local_index.json"
RAG_MANIFEST_PATH = RAG_PROCESSED_DIR / "manifest.json"


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    api_url: str
    api_key: str | None
    default_model: str
    proposal_model: str
    full_text_model: str
    rewrite_model: str
    timeout_seconds: float

    @classmethod
    def from_environment(cls) -> "ModelSettings":
        """Priority: explicit shell env > local .env.local file > defaults.

        Re-read on every construction, so saving the in-app model config takes
        effect on the next request without restarting the server.
        """
        local = load_local_env()

        def get(key: str, default: str = "") -> str:
            return (os.environ.get(key) or "").strip() or \
                (local.get(key) or "").strip() or default

        default = get("DEFAULT_MODEL", "default")
        return cls(
            provider=get("MODEL_PROVIDER", "openai_compatible"),
            api_url=get("MODEL_API_URL"),
            api_key=get("MODEL_API_KEY") or None,
            default_model=default,
            proposal_model=get("PROPOSAL_MODEL", default),
            full_text_model=get("FULL_TEXT_MODEL", default),
            rewrite_model=get("REWRITE_MODEL", default),
            timeout_seconds=float(get("MODEL_TIMEOUT_SECONDS", "300")),
        )

    def model_for(self, task_type: str) -> str:
        return {"PROPOSAL": self.proposal_model, "FULL_TEXT": self.full_text_model,
                "REWRITE": self.rewrite_model}.get(task_type, self.default_model)
