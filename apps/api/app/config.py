from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate the project-root .env regardless of the current working directory.
# Path: config.py -> app/ -> api/ -> apps/ -> project_root/
_ROOT_ENV = Path(__file__).resolve().parent.parent.parent.parent / ".env"
_ENV_KEY_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _resolve_env_files() -> tuple[str, ...]:
    files = [str(_ROOT_ENV)]

    raw_profile = (os.getenv("DEPLOY_PROFILE") or "").strip().lower()
    if not raw_profile:
        return tuple(files)

    profile_aliases = {
        "prod": "prd",
        "production": "prd",
        "runtime": "prd",
    }
    normalized = profile_aliases.get(raw_profile, raw_profile)

    # Support both canonical (dev/prd) and legacy (runtime) profile names.
    profile_candidates: list[str] = [normalized]
    if raw_profile != normalized:
        profile_candidates.append(raw_profile)

    seen: set[str] = set()
    for profile in profile_candidates:
        if profile in seen:
            continue
        seen.add(profile)
        profile_env = _ROOT_ENV.with_name(f".env.{profile}")
        if profile_env.exists():
            files.append(str(profile_env))

    return tuple(files)

logger = logging.getLogger(__name__)

_MANAGED_CONFIG_PREFIXES = (
    "DATABASE_",
    "PHOTO_",
    "THUMBNAIL_",
    "HOST_PHOTO_",
    "OPENAI_",
    "EMBEDDING_",
    "SEARCH_",
    "AI_",
    "AUTH_",
    "FACE_",
    "LOCATION_",
    "CORS_",
    "API_",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
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
    ai_vision_runtime: str = "llama-server"

    # ── The actual host-side path that is volume-mounted to photo_library_path ───
    # Defaults to photo_library_path when not explicitly set (local dev).
    host_photo_library_path: str = ""

    # ── Tunable numeric settings (safe to have defaults) ─────────────────────────
    thumbnail_size: int = 512
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Used by svc.sh to control uvicorn --reload flag; not used by the API itself.
    api_reload: bool = False
    ai_vision_max_tokens: int = 1200
    ai_vision_temperature: float = 0.1
    ai_max_retries: int = 3
    # Used by svc.sh/worker to control AI job concurrency; not read by the API.
    ai_worker_concurrency: int = 2
    scan_thumbnail_concurrency: int = 4
    scan_queue_max_size: int = 200
    scan_db_write_batch_size: int = 20
    scan_task_retry_limit: int = 3
    # Path prefix for model files used in .env variable expansion by svc.sh; not read by the API.
    ai_photo_lib_model_root: str = ""
    # Comma-separated list of allowed CORS origins.
    # Override in .env when deploying behind a reverse proxy or custom domain.
    cors_allow_origins: str = "http://localhost:5173,http://localhost:8088"

    # ── Local admin login / session ───────────────────────────────────────
    auth_enabled: bool = True
    auth_username: str = "admin"
    auth_password: str = ""
    auth_session_secret: str = ""
    auth_session_timeout_minutes: int = 30
    auth_cookie_secure: bool = False

    # ── Embedding / hybrid search config ─────────────────────────────────────
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimension: int = 1024
    embedding_timeout_seconds: int = 60
    search_vector_top_k: int = 200
    search_keyword_top_k: int = 2000
    search_rrf_k: int = 60
    search_vector_weight: float = 0.60
    search_keyword_weight: float = 0.40
    search_vector_min_score: float = 0.30
    search_content_vector_weight: float = 0.50
    search_tag_vector_weight: float = 0.25
    search_caption_vector_weight: float = 0.20
    search_ocr_vector_weight: float = 0.05
    query_planner_base_url: str = ""
    query_planner_alias: str = ""
    # ── Reverse geocoding / location enrichment ────────────────────────────
    location_resolver_provider: str = "none"
    location_resolver_endpoint: str = "https://nominatim.openstreetmap.org/reverse"
    location_resolver_timeout_seconds: int = 8
    location_resolver_user_agent: str = "ai-photo-lib/1.0"
    location_cache_rounding_decimals: int = 4

    # ── Derivative image settings ────────────────────────────────────────────
    # ai_thumbnail: small JPEG for VLM analysis and photo wall
    ai_thumbnail_max_edge: int = 768
    # face_work_image: medium-high res JPEG for face detection
    face_work_image_max_edge: int = 2048
    face_work_image_min_edge: int = 1280
    face_work_image_jpeg_quality: int = 94
    # face_crop: aligned square crop for face embedding / review UI
    face_crop_size: int = 112
    # Minimum face detection size (pixels on the shorter axis)
    face_min_detect_size: int = 40

    # ── Face / people recognition defaults ──────────────────────────────────
    face_recognition_enabled: bool = False
    face_provider: str = "opencv"
    face_detector_model: str = "yunet"
    face_embedding_model: str = "sface"
    face_runtime: str = "cpu"
    face_detector_model_path: str = ""
    face_embedding_model_path: str = ""
    store_face_crops: bool = True
    face_crop_storage: str = "local"
    face_auto_accept_threshold: float = 0.62
    face_review_threshold: float = 0.48
    face_cluster_threshold: float = 0.50
    face_min_face_size: int = 40
    face_min_detection_confidence: float = 0.75
    face_min_quality_for_prototype: float = 0.70
    face_max_positive_samples_per_person: int = 200
    face_allow_auto_assignment: bool = True
    face_require_human_confirmation_for_new_person: bool = True
    face_enable_negative_constraints: bool = True
    face_enable_person_cannot_links: bool = True
    face_auto_rematch_enabled: bool = True
    face_auto_rematch_schedule: str = "daily"
    face_auto_rematch_max_faces: int = 5000
    face_auto_rematch_check_interval_seconds: int = 3600

    @model_validator(mode="after")
    def _set_host_path_default(self) -> "Settings":
        if not self.host_photo_library_path:
            self.host_photo_library_path = self.photo_library_path
        return self


settings = Settings()


def _iter_env_file_keys(env_file: Path) -> set[str]:
    if not env_file.exists():
        return set()

    keys: set[str] = set()
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return keys


def _allowed_env_keys() -> set[str]:
    allowed: set[str] = set()
    for field_name in Settings.model_fields.keys():
        allowed.add(field_name)
        allowed.add(field_name.upper())
    return allowed


def get_unknown_config_keys(
    env_file: Path | None = None,
    *,
    managed_only: bool = False,
) -> list[str]:
    target = env_file or _ROOT_ENV
    env_keys = _iter_env_file_keys(target)
    if managed_only:
        env_keys = {
            key
            for key in env_keys
            if key.startswith(_MANAGED_CONFIG_PREFIXES)
        }
    unknown = sorted(k for k in env_keys if k not in _allowed_env_keys())
    return unknown


def warn_unknown_config_keys() -> None:
    unknown = get_unknown_config_keys()
    if not unknown:
        return
    logger.warning(
        "Unknown configuration keys detected in .env: %s. "
        "These keys are ignored today but will become startup errors in a future release.",
        ", ".join(unknown),
    )


def enforce_managed_config_keys(env_file: Path | None = None) -> None:
    """Fail explicitly when managed config keys are unknown.

    We only enforce for managed prefixes so deployment-level keys used by
    bootstrap scripts can continue to coexist in the shared repository .env.
    """
    unknown = get_unknown_config_keys(env_file, managed_only=True)
    if not unknown:
        return
    raise RuntimeError(
        "Unknown managed configuration keys in .env: "
        f"{', '.join(unknown)}. "
        "Remove them or add explicit Settings fields before startup."
    )
