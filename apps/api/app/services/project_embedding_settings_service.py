"""Service for managing per-project embedding configuration.

Project-level embedding settings are the authoritative source for:
- which endpoint to call for text embeddings
- which model to use
- API key, timeouts, and dimension constraints

Global config (settings.*) is only used as a fallback when no project-level
row has been created yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import ProjectEmbeddingSettings

logger = logging.getLogger(__name__)


def get_project_embedding_settings(
    db: Session,
    project_id: int,
) -> ProjectEmbeddingSettings | None:
    return (
        db.query(ProjectEmbeddingSettings)
        .filter(ProjectEmbeddingSettings.project_id == project_id)
        .first()
    )


def get_or_create_project_embedding_settings(
    db: Session,
    project_id: int,
) -> ProjectEmbeddingSettings:
    """Return existing settings or create a row from global config defaults.

    If global config has no embedding endpoint configured, creation is skipped
    and a RuntimeError is raised to prevent silently accepting unusable defaults.
    """
    row = get_project_embedding_settings(db, project_id)
    if row is not None:
        return row

    base_url = (settings.embedding_base_url or settings.openai_base_url or "").strip()
    if not base_url:
        raise RuntimeError(
            f"No embedding settings found for project_id={project_id} and "
            "global EMBEDDING_BASE_URL / OPENAI_BASE_URL is not configured. "
            "Configure embedding settings for this project via the API or set "
            "EMBEDDING_BASE_URL in your environment."
        )

    model_name = (settings.embedding_model or settings.openai_model or "").strip()
    if not model_name:
        raise RuntimeError(
            f"No embedding settings found for project_id={project_id} and "
            "global EMBEDDING_MODEL / OPENAI_MODEL is not configured. "
            "Configure embedding settings for this project via the API."
        )

    row = ProjectEmbeddingSettings(
        project_id=project_id,
        provider="openai-compatible",
        endpoint_url=base_url,
        api_key=settings.embedding_api_key or settings.openai_api_key or None,
        model_name=model_name,
        embedding_dimension=settings.embedding_dimension,
        batch_size=16,
        timeout_seconds=settings.embedding_timeout_seconds,
        input_prefix_query=None,
        input_prefix_document=None,
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Created default project_embedding_settings from global config. project_id=%s model=%s endpoint=%s",
        project_id,
        model_name,
        base_url,
    )
    return row


def update_project_embedding_settings(
    db: Session,
    project_id: int,
    payload: dict[str, Any],
) -> ProjectEmbeddingSettings:
    row = get_or_create_project_embedding_settings(db, project_id)

    allowed_fields = {
        "provider",
        "endpoint_url",
        "api_key",
        "model_name",
        "embedding_dimension",
        "batch_size",
        "timeout_seconds",
        "input_prefix_query",
        "input_prefix_document",
        "enabled",
    }
    for key, value in payload.items():
        if key in allowed_fields:
            setattr(row, key, value)

    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    logger.info(
        "Updated project_embedding_settings. project_id=%s fields=%s",
        project_id,
        sorted(payload.keys()),
    )
    return row


def resolve_embedding_settings(
    db: Session,
    project_id: int,
) -> dict[str, Any]:
    """Return a resolved dict of embedding parameters for this project.

    Merges project-level row with global config fallbacks so callers
    always have a fully-resolved set of parameters.
    """
    row = get_project_embedding_settings(db, project_id)

    if row is not None and row.enabled:
        return {
            "endpoint_url": row.endpoint_url,
            "api_key": row.api_key or settings.embedding_api_key or settings.openai_api_key,
            "model_name": row.model_name,
            "embedding_dimension": row.embedding_dimension,
            "timeout_seconds": row.timeout_seconds,
            "input_prefix_query": row.input_prefix_query,
            "input_prefix_document": row.input_prefix_document,
        }

    # Fallback to global config; raise if nothing usable is found
    base_url = (settings.embedding_base_url or settings.openai_base_url or "").strip()
    model_name = (settings.embedding_model or settings.openai_model or "").strip()

    if not base_url or not model_name:
        raise RuntimeError(
            f"Embedding is not configured for project_id={project_id}. "
            "Create project embedding settings via PUT /projects/{id}/embedding-settings."
        )

    return {
        "endpoint_url": base_url,
        "api_key": settings.embedding_api_key or settings.openai_api_key,
        "model_name": model_name,
        "embedding_dimension": settings.embedding_dimension,
        "timeout_seconds": settings.embedding_timeout_seconds,
        "input_prefix_query": None,
        "input_prefix_document": None,
    }
