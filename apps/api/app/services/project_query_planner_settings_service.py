"""Service for resolving project-scoped query planner runtime settings."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.ai import ProjectQueryPlannerSettings

logger = logging.getLogger(__name__)


def _default_query_planner_endpoint_url() -> str:
    return _as_text(global_settings.query_planner_base_url)


def _default_query_planner_model_name() -> str:
    return _as_text(global_settings.query_planner_alias)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def get_project_query_planner_settings(
    db: Session,
    project_id: int,
) -> Optional[ProjectQueryPlannerSettings]:
    """Read table-backed query planner settings.

    During rolling upgrade this table may be absent; return None instead of
    crashing search path so rule fallback remains available.
    """
    try:
        return (
            db.query(ProjectQueryPlannerSettings)
            .filter(ProjectQueryPlannerSettings.project_id == project_id)
            .first()
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning(
            "Query planner settings table unavailable; falling back to legacy settings. "
            "project_id=%s error=%s",
            project_id,
            exc,
        )
        return None


def get_or_create_project_query_planner_settings(
    db: Session,
    project_id: int,
) -> ProjectQueryPlannerSettings:
    """Return existing settings row, or create one from safe defaults."""
    row = get_project_query_planner_settings(db, project_id)
    if row is not None:
        return row

    row = ProjectQueryPlannerSettings(
        project_id=project_id,
        enabled=True,
        provider="llama-server",
        endpoint_url=_default_query_planner_endpoint_url(),
        api_key=global_settings.openai_api_key,
        model_name=_default_query_planner_model_name(),
        temperature=0.0,
        top_p=0.8,
        max_tokens=700,
        timeout_seconds=20,
        json_parse_strategy="strict_json_then_extract",
        planner_version="llm_query_planner_v1",
        prompt_template="",
        system_prompt="",
        fallback_mode="rule_fallback",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Created default project_query_planner_settings for project_id=%s",
        project_id,
    )
    return row


def update_project_query_planner_settings(
    db: Session,
    project_id: int,
    updates: dict[str, Any],
) -> ProjectQueryPlannerSettings:
    row = get_or_create_project_query_planner_settings(db, project_id)

    allowed_fields = {
        "enabled",
        "provider",
        "endpoint_url",
        "api_key",
        "model_name",
        "temperature",
        "top_p",
        "max_tokens",
        "timeout_seconds",
        "json_parse_strategy",
        "planner_version",
        "prompt_template",
        "system_prompt",
        "fallback_mode",
    }
    for key, value in updates.items():
        if key not in allowed_fields:
            raise ValueError(f"Unknown query planner settings field: {key!r}")
        setattr(row, key, value)

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def reset_project_query_planner_settings(
    db: Session,
    project_id: int,
) -> ProjectQueryPlannerSettings:
    row = get_project_query_planner_settings(db, project_id)
    if row is not None:
        db.delete(row)
        db.commit()
        logger.info(
            "Deleted project_query_planner_settings for project_id=%s (reset to defaults)",
            project_id,
        )
    return get_or_create_project_query_planner_settings(db, project_id)


def resolve_query_planner_settings(
    db: Session,
    project_id: int,
    *,
    search_quality_settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resolve effective query planner settings.

    Priority:
    1. project_query_planner_settings table
    2. project_search_settings.search_quality_settings (legacy compatibility)
    3. global .env defaults
    """
    defaults = {
        "enabled": True,
        "provider": "llama-server",
        "endpoint_url": _default_query_planner_endpoint_url(),
        "api_key": "",
        "model_name": _default_query_planner_model_name(),
        "temperature": 0.0,
        "top_p": 0.8,
        "max_tokens": 700,
        "timeout_seconds": 20,
        "json_parse_strategy": "strict_json_then_extract",
        "planner_version": "llm_query_planner_v1",
        "prompt_template": "",
        "system_prompt": "",
        "fallback_mode": "rule_fallback",
    }

    row = get_project_query_planner_settings(db, project_id)
    if row is not None:
        return {
            "enabled": bool(row.enabled),
            "provider": _as_text(row.provider, defaults["provider"]),
            "endpoint_url": _as_text(row.endpoint_url),
            "api_key": _as_text(row.api_key, defaults["api_key"]),
            "model_name": _as_text(row.model_name),
            "temperature": _as_float(row.temperature, defaults["temperature"]),
            "top_p": _as_float(row.top_p, defaults["top_p"]),
            "max_tokens": _as_int(row.max_tokens, defaults["max_tokens"]),
            "timeout_seconds": _as_int(row.timeout_seconds, defaults["timeout_seconds"]),
            "json_parse_strategy": _as_text(
                row.json_parse_strategy,
                defaults["json_parse_strategy"],
            ),
            "planner_version": _as_text(row.planner_version, defaults["planner_version"]),
            "prompt_template": _as_text(row.prompt_template, defaults["prompt_template"]),
            "system_prompt": _as_text(row.system_prompt, defaults["system_prompt"]),
            "fallback_mode": _as_text(row.fallback_mode, defaults["fallback_mode"]),
        }

    legacy = search_quality_settings or {}
    return {
        "enabled": _as_bool(legacy.get("query_planner_enabled"), defaults["enabled"]),
        "provider": _as_text(legacy.get("query_planner_provider"), defaults["provider"]),
        "endpoint_url": _as_text(
            legacy.get("query_planner_endpoint_url"),
            defaults["endpoint_url"],
        ),
        "api_key": _as_text(legacy.get("query_planner_api_key"), defaults["api_key"]),
        "model_name": _as_text(
            legacy.get("query_planner_model_name"),
            defaults["model_name"],
        ),
        "temperature": _as_float(
            legacy.get("query_planner_temperature"),
            defaults["temperature"],
        ),
        "top_p": _as_float(legacy.get("query_planner_top_p"), defaults["top_p"]),
        "max_tokens": _as_int(
            legacy.get("query_planner_max_tokens"),
            defaults["max_tokens"],
        ),
        "timeout_seconds": _as_int(
            legacy.get("query_planner_timeout_seconds"),
            defaults["timeout_seconds"],
        ),
        "json_parse_strategy": _as_text(
            legacy.get("query_planner_json_parse_strategy"),
            defaults["json_parse_strategy"],
        ),
        "planner_version": _as_text(
            legacy.get("query_planner_planner_version"),
            defaults["planner_version"],
        ),
        "prompt_template": _as_text(
            legacy.get("query_planner_prompt_template"),
            defaults["prompt_template"],
        ),
        "system_prompt": _as_text(
            legacy.get("query_planner_system_prompt"),
            defaults["system_prompt"],
        ),
        "fallback_mode": _as_text(
            legacy.get("query_planner_fallback_mode"),
            defaults["fallback_mode"],
        ),
    }
