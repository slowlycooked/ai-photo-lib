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
from ..models.user import AIServiceProfile

logger = logging.getLogger(__name__)

DEFAULT_INPUT_PREFIX_QUERY = (
    "Represent this search query for retrieving relevant photo descriptions"
)
DEFAULT_INPUT_PREFIX_DOCUMENT = "Represent this photo description for retrieval"


def _resolved_prefix(value: str | None, default_value: str) -> str:
    if value is None:
        return default_value
    text = value.strip()
    return text if text else default_value


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
        ai_service_profile_id=None,
        provider="openai-compatible",
        endpoint_url=base_url,
        api_key=settings.embedding_api_key or settings.openai_api_key or None,
        model_name=model_name,
        embedding_dimension=settings.embedding_dimension,
        batch_size=16,
        timeout_seconds=settings.embedding_timeout_seconds,
        input_prefix_query=DEFAULT_INPUT_PREFIX_QUERY,
        input_prefix_document=DEFAULT_INPUT_PREFIX_DOCUMENT,
        enabled=True,
        search_content_vector_weight=settings.search_content_vector_weight,
        search_tag_vector_weight=settings.search_tag_vector_weight,
        search_caption_vector_weight=settings.search_caption_vector_weight,
        search_ocr_vector_weight=settings.search_ocr_vector_weight,
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
        "ai_service_profile_id",
        "endpoint_url",
        "api_key",
        "model_name",
        "embedding_dimension",
        "batch_size",
        "timeout_seconds",
        "input_prefix_query",
        "input_prefix_document",
        "enabled",
        "search_content_vector_weight",
        "search_tag_vector_weight",
        "search_caption_vector_weight",
        "search_ocr_vector_weight",
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
    """Compatibility resolver.

    Prefer ``resolve_embedding_settings_strict`` for runtime paths that must
    fail explicitly when project-level settings are missing.
    """
    try:
        return resolve_embedding_settings_strict(db, project_id)
    except RuntimeError:
        # Compatibility fallback for legacy call sites only.
        pass

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
        "input_prefix_query": DEFAULT_INPUT_PREFIX_QUERY,
        "input_prefix_document": DEFAULT_INPUT_PREFIX_DOCUMENT,
        "search_field_weights": {
            "content_embedding": settings.search_content_vector_weight,
            "tag_embedding": settings.search_tag_vector_weight,
            "caption_embedding": settings.search_caption_vector_weight,
            "ocr_embedding": settings.search_ocr_vector_weight,
        },
    }


def resolve_embedding_settings_strict(
    db: Session,
    project_id: int,
) -> dict[str, Any]:
    """Return project-level embedding parameters without global fallback."""
    row = get_project_embedding_settings(db, project_id)

    if row is None:
        raise RuntimeError(
            f"Embedding is not configured for project_id={project_id}. "
            "Create project embedding settings via PUT /projects/{id}/embedding-settings."
        )
    if not row.enabled:
        raise RuntimeError(
            f"Embedding is disabled for project_id={project_id}. "
            "Enable it via PUT /projects/{id}/embedding-settings."
        )

    endpoint_url = (row.endpoint_url or "").strip()
    model_name = (row.model_name or "").strip()
    api_key = row.api_key
    if row.ai_service_profile_id is not None:
        profile = (
            db.query(AIServiceProfile)
            .filter(
                AIServiceProfile.id == row.ai_service_profile_id,
                AIServiceProfile.enabled.is_(True),
            )
            .first()
        )
        if profile is None:
            raise RuntimeError(
                f"AI service profile {row.ai_service_profile_id} is not available for project_id={project_id}."
            )
        if profile.capability != "embedding":
            raise RuntimeError(
                f"AI service profile {profile.id} has capability={profile.capability!r}; expected 'embedding'."
            )
        endpoint_url = (profile.endpoint_url or "").strip()
        model_name = (profile.model_name or "").strip()
        api_key = profile.api_key
    if not endpoint_url or not model_name:
        raise RuntimeError(
            f"Embedding settings for project_id={project_id} are incomplete. "
            "Both endpoint_url and model_name are required."
        )

    return {
        "endpoint_url": endpoint_url,
        "api_key": api_key,
        "model_name": model_name,
        "embedding_dimension": row.embedding_dimension,
        "timeout_seconds": row.timeout_seconds,
        "input_prefix_query": _resolved_prefix(
            row.input_prefix_query,
            DEFAULT_INPUT_PREFIX_QUERY,
        ),
        "input_prefix_document": _resolved_prefix(
            row.input_prefix_document,
            DEFAULT_INPUT_PREFIX_DOCUMENT,
        ),
        "search_field_weights": {
            "content_embedding": row.search_content_vector_weight,
            "tag_embedding": row.search_tag_vector_weight,
            "caption_embedding": row.search_caption_vector_weight,
            "ocr_embedding": row.search_ocr_vector_weight,
        },
    }
