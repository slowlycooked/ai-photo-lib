"""Service for managing per-project search settings."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.project_search_settings import ProjectSearchSettings
from ..services.search.result_cache import bump_project_search_cache_epoch
from ..services.search.types import (
    DEFAULT_SEARCH_RESULT_CACHE_TTL_SECONDS,
    DEFAULT_KEYWORD_FIELD_WEIGHTS,
    DEFAULT_OCR_VECTOR_FIELD_WEIGHTS,
    DEFAULT_VECTOR_FIELD_WEIGHTS,
)

logger = logging.getLogger(__name__)


def get_project_search_settings(
    db: Session, project_id: int
) -> Optional[ProjectSearchSettings]:
    """Return the search settings row for a project, or None."""
    return (
        db.query(ProjectSearchSettings)
        .filter(ProjectSearchSettings.project_id == project_id)
        .first()
    )


def get_or_create_project_search_settings(
    db: Session, project_id: int
) -> ProjectSearchSettings:
    """Return existing settings row, or create one from config defaults."""
    row = get_project_search_settings(db, project_id)
    if row is not None:
        return row

    row = ProjectSearchSettings(
        project_id=project_id,
        default_mode="hybrid",
        keyword_top_k=global_settings.search_keyword_top_k,
        vector_top_k=global_settings.search_vector_top_k,
        page_size_default=50,
        page_size_max=200,
        rrf_k=global_settings.search_rrf_k,
        keyword_weight=global_settings.search_keyword_weight,
        vector_weight=global_settings.search_vector_weight,
        vector_min_score=global_settings.search_vector_min_score,
        keyword_field_weights=dict(DEFAULT_KEYWORD_FIELD_WEIGHTS),
        vector_field_weights=dict(DEFAULT_VECTOR_FIELD_WEIGHTS),
        ocr_query_vector_field_weights=dict(DEFAULT_OCR_VECTOR_FIELD_WEIGHTS),
        enable_query_understanding=True,
        enable_structured_filters=False,
        enable_semantic_tag_boost=False,
        search_result_cache_ttl_seconds=DEFAULT_SEARCH_RESULT_CACHE_TTL_SECONDS,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info(
        "Created default project_search_settings for project_id=%s", project_id
    )
    return row


def update_project_search_settings(
    db: Session,
    project_id: int,
    updates: dict,
) -> ProjectSearchSettings:
    """Upsert search settings for a project with *updates* applied."""
    row = get_or_create_project_search_settings(db, project_id)

    allowed_fields = {
        "default_mode",
        "keyword_top_k",
        "vector_top_k",
        "page_size_default",
        "page_size_max",
        "rrf_k",
        "keyword_weight",
        "vector_weight",
        "vector_min_score",
        "keyword_field_weights",
        "vector_field_weights",
        "ocr_query_vector_field_weights",
        "enable_query_understanding",
        "enable_structured_filters",
        "enable_semantic_tag_boost",
        "search_result_cache_ttl_seconds",
        "search_quality_settings",
    }
    for key, value in updates.items():
        if key not in allowed_fields:
            raise ValueError(f"Unknown search settings field: {key!r}")
        setattr(row, key, value)

    bump_project_search_cache_epoch(
        db,
        project_id,
        reason="project_search_settings_updated",
    )
    db.commit()
    db.refresh(row)
    return row


def reset_project_search_settings(
    db: Session, project_id: int
) -> ProjectSearchSettings:
    """Delete the custom settings row (if any), triggering config-level defaults."""
    row = get_project_search_settings(db, project_id)
    if row is not None:
        db.delete(row)
        bump_project_search_cache_epoch(
            db,
            project_id,
            reason="project_search_settings_reset",
        )
        db.commit()
        logger.info(
            "Deleted project_search_settings for project_id=%s (reset to defaults)",
            project_id,
        )
    return get_or_create_project_search_settings(db, project_id)
