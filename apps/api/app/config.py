from __future__ import annotations

from pathlib import Path

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

    database_url: str = "postgresql+psycopg://photo:photo@localhost:5432/photo"
    photo_library_path: str = "/photos"
    # The actual host-side path that is volume-mounted to photo_library_path inside
    # the container. Used only to display user-friendly paths in the UI.
    # Defaults to photo_library_path when not explicitly set (e.g. local dev).
    host_photo_library_path: str = ""
    thumbnail_path: str = "/data/thumbs"
    thumbnail_size: int = 512
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # OpenAI-compatible AI settings
    openai_api_key: str = "sk-local"
    openai_base_url: str = "http://127.0.0.1:8082/v1"
    openai_model: str = "MiniCPM-V-4.6"
    openai_vision_model: str = "MiniCPM-V-4.6"
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
