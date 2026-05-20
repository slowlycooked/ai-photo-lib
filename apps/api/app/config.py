from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the project-root .env regardless of the current working directory.
# Path: config.py -> app/ -> api/ -> apps/ -> project_root/
_ROOT_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Infrastructure (required, no defaults — must come from .env or env vars) ──
    database_url: str
    # Global fallback photo library path used by the legacy /scan endpoint and
    # when creating the initial default project during DB migration.
    # All project-specific paths are stored in the projects table.
    photo_library_path: str
    thumbnail_path: str

    # ── AI endpoint (required, no defaults — must come from env) ─────────────────
    # These values are used only when initialising a new project's AI settings
    # row. Once a project exists its settings row is the authoritative source.
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_vision_model: str

    # ── The actual host-side path that is volume-mounted to photo_library_path ───
    # Defaults to photo_library_path when not explicitly set (local dev).
    host_photo_library_path: str = ""

    # ── Tunable numeric settings (safe to have defaults) ─────────────────────────
    thumbnail_size: int = 512
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    ai_vision_max_tokens: int = 512
    ai_vision_temperature: float = 0.0
    ai_max_retries: int = 3
    ai_worker_concurrency: int = 1

    @model_validator(mode="after")
    def _set_host_path_default(self) -> "Settings":
        if not self.host_photo_library_path:
            self.host_photo_library_path = self.photo_library_path
        return self


settings = Settings()
