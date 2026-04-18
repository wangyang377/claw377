from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

APP_NAME = "claw377"
APP_HOME_ENV = "CLAW_HOME"


def current_workspace() -> Path:
    return Path.cwd().resolve()


def app_home() -> Path:
    configured = os.environ.get(APP_HOME_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / f".{APP_NAME}").resolve()


def config_env_path() -> Path:
    return app_home() / "config.env"


def sessions_dir() -> Path:
    return app_home() / "sessions"


def transcripts_dir() -> Path:
    return app_home() / "transcripts"


def workspace_state_dir(workspace: Path | None = None) -> Path:
    resolved = (workspace or current_workspace()).resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return app_home() / "workspaces" / digest


def tasks_dir(workspace: Path | None = None) -> Path:
    return workspace_state_dir(workspace) / "tasks"


def ensure_app_layout() -> None:
    for path in (
        app_home(),
        sessions_dir(),
        transcripts_dir(),
        app_home() / "workspaces",
        tasks_dir(),
    ):
        path.mkdir(parents=True, exist_ok=True)


def ensure_default_config() -> Path:
    path = config_env_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# Global claw377 configuration",
                "# Fill in MODEL_NAME and the provider API key you need.",
                "MODEL_NAME=",
                "XAI_API_KEY=",
                "OPENAI_API_KEY=",
                "ANTHROPIC_API_KEY=",
                "TAVILY_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def load_environment() -> None:
    ensure_app_layout()
    load_dotenv(ensure_default_config(), override=False)
    load_dotenv(current_workspace() / ".env", override=True)


def environment_status() -> tuple[bool, list[str]]:
    missing: list[str] = []
    model = os.environ.get("MODEL_NAME") or os.environ.get("LITELLM_MODEL")
    if not model:
        missing.append("MODEL_NAME or LITELLM_MODEL")
    provider_keys = (
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "DEEPSEEK_API_KEY",
    )
    if not any(os.environ.get(name, "").strip() for name in provider_keys):
        missing.append("one provider API key (for example XAI_API_KEY)")
    return not missing, missing
