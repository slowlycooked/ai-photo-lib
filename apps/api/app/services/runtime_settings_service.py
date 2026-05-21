from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from ..core.debug_config import (
    DEBUG_MATRIX_FIELDS,
    build_preset_matrix,
    legacy_debug_level_to_mode,
    normalize_debug_mode_safe,
    normalize_log_level_safe,
)
from ..logging_config import apply_debug_config
from ..models.app_settings import AppSettings
from ..schemas.debug_config import DebugConfig, DebugConfigUpdate, DebugMatrix, StoredDebugConfig, build_default_debug_config

logger = logging.getLogger(__name__)


class RuntimeSettingsStorageUnavailableError(RuntimeError):
    """Raised when runtime settings storage is unavailable (e.g. missing table)."""


def _is_missing_app_settings_table_error(exc: Exception) -> bool:
    missing_strings = (
        'relation "app_settings" does not exist',
        "no such table: app_settings",
    )
    missing_type_names = frozenset({"UndefinedTable", "UndefinedRelation"})

    chain: list[Exception] = []
    node: Exception | None = exc
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        chain.append(node)
        seen.add(id(node))
        node = getattr(node, "__cause__", None) or getattr(node, "__context__", None)

    for err in chain:
        if isinstance(err, ProgrammingError) and any(text in str(err).lower() for text in missing_strings):
            return True
        if type(err).__name__ in missing_type_names:
            return True
        module = getattr(type(err), "__module__", "") or ""
        if "psycopg" in module and any(text in str(err).lower() for text in missing_strings):
            return True

    return False


def _camel_to_snake_key(value: str) -> str:
    chars: list[str] = []
    for ch in value:
        if ch.isupper():
            chars.append("_")
            chars.append(ch.lower())
        else:
            chars.append(ch)
    return "".join(chars).lstrip("_")


def _normalize_raw_keys(raw: dict) -> dict:
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        snake_key = _camel_to_snake_key(str(key))
        if isinstance(value, dict):
            normalized[snake_key] = _normalize_raw_keys(value)
        else:
            normalized[snake_key] = value
    return normalized


def _extract_raw_mode(raw: dict) -> str:
    if raw.get("debug_mode") is not None:
        return normalize_debug_mode_safe(raw.get("debug_mode"))
    if raw.get("debug_level") is not None:
        return legacy_debug_level_to_mode(raw.get("debug_level"))
    return "BASIC"


def _extract_raw_matrix(raw: dict, *, mode: str) -> dict[str, str]:
    default_matrix = build_preset_matrix(mode if mode != "CUSTOM" else "BASIC")
    source = raw.get("debug_matrix") if isinstance(raw.get("debug_matrix"), dict) else raw
    matrix: dict[str, str] = {}
    for field in DEBUG_MATRIX_FIELDS:
        fallback = default_matrix[field]
        matrix[field] = normalize_log_level_safe(
            source.get(field),
            fallback=fallback,
            setting_key="global_debug_config",
            field_name=field,
        )
    return matrix


def _sanitise_stored_config(raw: dict, *, updated_at: datetime | None = None) -> StoredDebugConfig:
    normalized_raw = _normalize_raw_keys(raw)
    mode = _extract_raw_mode(normalized_raw)
    if mode == "CUSTOM":
        matrix = _extract_raw_matrix(normalized_raw, mode="CUSTOM")
    elif "debug_matrix" in normalized_raw or any(field in normalized_raw for field in DEBUG_MATRIX_FIELDS):
        if normalized_raw.get("debug_mode") == "CUSTOM":
            matrix = _extract_raw_matrix(normalized_raw, mode="CUSTOM")
            mode = "CUSTOM"
        else:
            matrix = build_preset_matrix(mode)
    else:
        matrix = build_preset_matrix(mode)

    return StoredDebugConfig(
        debug_mode=mode,
        debug_matrix=DebugMatrix(**matrix),
        updated_at=updated_at,
    )


def _to_response_model(config: StoredDebugConfig) -> DebugConfig:
    return DebugConfig(
        debug_mode=config.debug_mode,
        debug_matrix=config.debug_matrix,
        updated_at=config.updated_at,
    )


class RuntimeSettingsService:
    _debug_config_cache: DebugConfig | None = None
    _cache_expire = 10
    _last_load: float = 0
    _lock = threading.Lock()
    _setting_key = "global_debug_config"

    @classmethod
    def get_debug_config(cls, db: Session) -> DebugConfig:
        now = time.time()
        with cls._lock:
            if cls._debug_config_cache and now - cls._last_load < cls._cache_expire:
                return cls._debug_config_cache
            try:
                row = db.query(AppSettings).filter(AppSettings.key == cls._setting_key).first()
            except Exception as exc:  # noqa: BLE001
                if _is_missing_app_settings_table_error(exc):
                    logger.error(
                        "Runtime settings table missing (endpoint=/settings/debug, setting_key=%s).",
                        cls._setting_key,
                    )
                    raise RuntimeSettingsStorageUnavailableError(
                        "Missing required database table: app_settings. Run 'alembic upgrade head' to apply the pending migration."
                    ) from exc
                logger.error(
                    "Unexpected error loading debug config (endpoint=/settings/debug, setting_key=%s): %s",
                    cls._setting_key,
                    exc,
                )
                raise RuntimeSettingsStorageUnavailableError(
                    f"Failed to load debug configuration from database: {exc}"
                ) from exc

            stored = _sanitise_stored_config(
                row.value_json if row else {},
                updated_at=(row.updated_at if row else None),
            )
            config = _to_response_model(stored if row else build_default_debug_config())
            cls._debug_config_cache = config
            cls._last_load = now
            return config

    @classmethod
    def set_debug_config(cls, db: Session, payload: DebugConfigUpdate) -> DebugConfig:
        with cls._lock:
            try:
                row = db.query(AppSettings).filter(AppSettings.key == cls._setting_key).first()
            except Exception as exc:  # noqa: BLE001
                if _is_missing_app_settings_table_error(exc):
                    logger.error(
                        "Runtime settings table missing (endpoint=PUT /settings/debug, setting_key=%s).",
                        cls._setting_key,
                    )
                    raise RuntimeSettingsStorageUnavailableError(
                        "Missing required database table: app_settings. Run 'alembic upgrade head' to apply the pending migration."
                    ) from exc
                logger.error(
                    "Unexpected error saving debug config (endpoint=PUT /settings/debug, setting_key=%s): %s",
                    cls._setting_key,
                    exc,
                )
                raise RuntimeSettingsStorageUnavailableError(
                    f"Failed to save debug configuration to database: {exc}"
                ) from exc

            resolved_matrix = (
                payload.debug_matrix.model_dump()
                if payload.debug_mode == "CUSTOM"
                else build_preset_matrix(payload.debug_mode)
            )
            updated_at = datetime.now(timezone.utc)
            stored = StoredDebugConfig(
                debug_mode=payload.debug_mode,
                debug_matrix=DebugMatrix(**resolved_matrix),
                updated_at=updated_at,
            )

            if row:
                row.value_json = stored.model_dump(mode="json")
                row.updated_at = updated_at
            else:
                row = AppSettings(
                    key=cls._setting_key,
                    value_json=stored.model_dump(mode="json"),
                    updated_at=updated_at,
                )
                db.add(row)
            db.commit()

            response = _to_response_model(stored)
            cls._debug_config_cache = response
            cls._last_load = time.time()
            apply_debug_config(response)
            return response

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._debug_config_cache = None
            cls._last_load = 0
