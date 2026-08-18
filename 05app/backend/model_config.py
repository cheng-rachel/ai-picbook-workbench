"""Local model-service configuration stored in .env.local.

Product-level replacement for manual `export` in the shell. Scope is one
provider: all tasks share MODEL_API_URL / MODEL_API_KEY, and the three
task-specific models fall back to DEFAULT_MODEL when blank (existing
ModelSettings behavior). The API key is never echoed back in full.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import env_local_path, load_local_env

REQUIRED_FIELDS = ("MODEL_PROVIDER", "MODEL_API_URL", "MODEL_API_KEY", "DEFAULT_MODEL")
OPTIONAL_FIELDS = ("PROPOSAL_MODEL", "FULL_TEXT_MODEL", "REWRITE_MODEL")
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
_HEADER = ("# Power Up 绘编本地模型配置。此文件包含真实 API Key：不要提交、分享或截图。\n"
           "# 优先级：当前 shell 环境变量 > 本文件 > 程序默认值。\n")


def read_model_config() -> dict:
    """Display-safe view: the API key is reported as set/unset plus a tail hint."""
    stored = load_local_env()
    values = {key: (os.environ.get(key) or stored.get(key) or "").strip()
              for key in ALL_FIELDS}
    api_key = values.pop("MODEL_API_KEY")
    return {
        "ok": True,
        "configured": bool(api_key and values["MODEL_API_URL"]),
        "api_key_set": bool(api_key),
        "api_key_hint": ("…" + api_key[-4:]) if len(api_key) >= 8 else ("已设置" if api_key else ""),
        "env_overrides": [key for key in ALL_FIELDS if (os.environ.get(key) or "").strip()],
        **{key.lower(): value for key, value in values.items()},
    }


def save_model_config(data: dict) -> dict:
    """Validate and write .env.local (0600). Blank API key keeps the stored one."""
    stored = load_local_env()
    values = {}
    for key in ALL_FIELDS:
        raw = data.get(key.lower(), data.get(key, ""))
        values[key] = str(raw or "").strip()
    if not values["MODEL_API_KEY"]:
        values["MODEL_API_KEY"] = (stored.get("MODEL_API_KEY") or "").strip()
    missing = [key for key in REQUIRED_FIELDS if not values[key]]
    if missing:
        return {"ok": False, "error_code": "CONFIG_FIELDS_REQUIRED",
                "message": "请填写必填项：" + "、".join(missing)}
    if "\n" in "".join(values.values()):
        return {"ok": False, "error_code": "CONFIG_INVALID_VALUE",
                "message": "配置值不能包含换行"}
    path = env_local_path()
    lines = [_HEADER] + [f"{key}={values[key]}\n" for key in ALL_FIELDS if values[key]]
    path.write_text("".join(lines), encoding="utf-8")
    os.chmod(path, 0o600)
    return {"ok": True, "configured": True, "saved_to": path.name}
