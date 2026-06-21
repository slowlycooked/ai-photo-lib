"""SQLAlchemy model for per-project search configuration."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# ── Default JSON values (stored as server defaults / used when no row exists) ─

_DEFAULT_KEYWORD_FIELD_WEIGHTS = (
    '{"caption": 3, "ocr_text": 5, "scene_tags": 4, "object_tags": 4, '
    '"activity_tags": 4, "search_keywords": 4, "quality_tags": 2, '
    '"location_clues": 2, "file_name": 1}'
)
_DEFAULT_VECTOR_FIELD_WEIGHTS = (
    '{"content_embedding": 0.5, "tag_embedding": 0.25, '
    '"caption_embedding": 0.2, "ocr_embedding": 0.05}'
)
_DEFAULT_OCR_VECTOR_FIELD_WEIGHTS = (
    '{"content_embedding": 0.35, "tag_embedding": 0.15, '
    '"caption_embedding": 0.1, "ocr_embedding": 0.4}'
)


class ProjectSearchSettings(Base):
    """Per-project search hyper-parameters.

    Priority in SearchSettingsResolver:
      1. This table (highest)
      2. project_embedding_settings.search_*_vector_weight columns
      3. config.py search_* defaults (lowest)
    """

    __tablename__ = "project_search_settings"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", name="uq_project_search_settings_project_id"
        ),
        sa.Index("ix_project_search_settings_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Search mode & recall sizing ───────────────────────────────────────────
    default_mode: Mapped[str] = mapped_column(
        Text, server_default="hybrid", nullable=False
    )
    keyword_top_k: Mapped[int] = mapped_column(
        Integer, server_default="2000", nullable=False
    )
    vector_top_k: Mapped[int] = mapped_column(
        Integer, server_default="200", nullable=False
    )
    page_size_default: Mapped[int] = mapped_column(
        Integer, server_default="50", nullable=False
    )
    page_size_max: Mapped[int] = mapped_column(
        Integer, server_default="200", nullable=False
    )

    # ── Fusion parameters ─────────────────────────────────────────────────────
    rrf_k: Mapped[int] = mapped_column(Integer, server_default="60", nullable=False)
    keyword_weight: Mapped[float] = mapped_column(
        Float, server_default="0.55", nullable=False
    )
    vector_weight: Mapped[float] = mapped_column(
        Float, server_default="0.45", nullable=False
    )
    vector_min_score: Mapped[float] = mapped_column(
        Float, server_default="0.25", nullable=False
    )

    # ── Field weights (JSONB) ─────────────────────────────────────────────────
    keyword_field_weights: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default=_DEFAULT_KEYWORD_FIELD_WEIGHTS, nullable=True
    )
    vector_field_weights: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default=_DEFAULT_VECTOR_FIELD_WEIGHTS, nullable=True
    )
    ocr_query_vector_field_weights: Mapped[Optional[dict]] = mapped_column(
        JSONB, server_default=_DEFAULT_OCR_VECTOR_FIELD_WEIGHTS, nullable=True
    )

    # ── Feature flags ─────────────────────────────────────────────────────────
    enable_query_understanding: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    enable_structured_filters: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    enable_semantic_tag_boost: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    search_result_cache_ttl_seconds: Mapped[int] = mapped_column(
        Integer, server_default="600", nullable=False
    )

    # ── Evidence / quality settings (JSONB) ───────────────────────────────────
    # Overrides for vector_strict_score, min_display_evidence_level, etc.
    # See EffectiveSearchSettings for supported keys.
    search_quality_settings: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )
