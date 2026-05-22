"""SearchSettingsResolver — merges project_search_settings / config into EffectiveSearchSettings.

Priority:
  1. project_search_settings row (highest)
  2. project_embedding_settings.search_*_vector_weight columns
  3. config.py search_* defaults (lowest)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ...config import settings as global_settings
from ...models.ai import ProjectEmbeddingSettings
from ...models.project_search_settings import ProjectSearchSettings
from .types import (
    DEFAULT_KEYWORD_FIELD_WEIGHTS,
    DEFAULT_OCR_VECTOR_FIELD_WEIGHTS,
    DEFAULT_VECTOR_FIELD_WEIGHTS,
    EffectiveSearchSettings,
    SearchMode,
)

logger = logging.getLogger(__name__)


class SearchSettingsResolver:
    """Resolve effective search settings for a project."""

    # ── Defaults ──────────────────────────────────────────────────────────────

    @staticmethod
    def defaults() -> EffectiveSearchSettings:
        """Build EffectiveSearchSettings from global config defaults only."""
        return EffectiveSearchSettings(
            default_mode="hybrid",
            keyword_top_k=global_settings.search_keyword_top_k,
            vector_top_k=global_settings.search_vector_top_k,
            rrf_k=global_settings.search_rrf_k,
            keyword_weight=global_settings.search_keyword_weight,
            vector_weight=global_settings.search_vector_weight,
            vector_min_score=global_settings.search_vector_min_score,
            keyword_field_weights=dict(DEFAULT_KEYWORD_FIELD_WEIGHTS),
            vector_field_weights=dict(DEFAULT_VECTOR_FIELD_WEIGHTS),
            ocr_vector_field_weights=dict(DEFAULT_OCR_VECTOR_FIELD_WEIGHTS),
            enable_query_understanding=True,
            enable_structured_filters=False,
            enable_semantic_tag_boost=True,  # P3: enabled by default
        )

    # ── Main resolver ─────────────────────────────────────────────────────────

    @staticmethod
    def resolve(db: Session, project_id: int) -> EffectiveSearchSettings:
        """Return the effective search settings for *project_id*."""

        # 1. project_search_settings (highest priority)
        row: Optional[ProjectSearchSettings] = (
            db.query(ProjectSearchSettings)
            .filter(ProjectSearchSettings.project_id == project_id)
            .first()
        )
        if row is not None:
            # Read optional search_quality_settings JSONB overrides
            _q: dict = row.search_quality_settings or {}
            return EffectiveSearchSettings(
                default_mode=_safe_mode(row.default_mode),
                keyword_top_k=row.keyword_top_k,
                vector_top_k=row.vector_top_k,
                rrf_k=row.rrf_k,
                keyword_weight=row.keyword_weight,
                vector_weight=row.vector_weight,
                vector_min_score=row.vector_min_score,
                keyword_field_weights=dict(
                    row.keyword_field_weights or DEFAULT_KEYWORD_FIELD_WEIGHTS
                ),
                vector_field_weights=_normalise_vector_weights(
                    row.vector_field_weights or DEFAULT_VECTOR_FIELD_WEIGHTS
                ),
                ocr_vector_field_weights=_normalise_vector_weights(
                    row.ocr_query_vector_field_weights or DEFAULT_OCR_VECTOR_FIELD_WEIGHTS
                ),
                enable_query_understanding=row.enable_query_understanding,
                enable_structured_filters=row.enable_structured_filters,
                enable_semantic_tag_boost=row.enable_semantic_tag_boost,
                # Evidence quality overrides from JSONB (fall back to dataclass defaults)
                vector_strict_score=float(_q.get("vector_strict_score", 0.42)),
                min_display_evidence_level=str(_q.get("min_display_evidence_level", "C")),
                enable_evidence_filter=bool(_q.get("enable_evidence_filter", True)),
                enable_negative_penalty=bool(_q.get("enable_negative_penalty", True)),
                evidence_weight=float(_q.get("evidence_weight", 0.02)),
                negative_term_penalty=float(_q.get("negative_term_penalty", 0.01)),
            )

        # 2. project_embedding_settings (partial fallback — vector weights only)
        embed_row: Optional[ProjectEmbeddingSettings] = (
            db.query(ProjectEmbeddingSettings)
            .filter(ProjectEmbeddingSettings.project_id == project_id)
            .first()
        )
        if embed_row is not None:
            vector_weights: dict[str, float] = _normalise_vector_weights({
                "content_embedding": embed_row.search_content_vector_weight,
                "tag_embedding": embed_row.search_tag_vector_weight,
                "caption_embedding": embed_row.search_caption_vector_weight,
                "ocr_embedding": embed_row.search_ocr_vector_weight,
            })
        else:
            vector_weights = _normalise_vector_weights({
                "content_embedding": global_settings.search_content_vector_weight,
                "tag_embedding": global_settings.search_tag_vector_weight,
                "caption_embedding": global_settings.search_caption_vector_weight,
                "ocr_embedding": global_settings.search_ocr_vector_weight,
            })

        # 3. Global config for everything else
        return EffectiveSearchSettings(
            default_mode="hybrid",
            keyword_top_k=global_settings.search_keyword_top_k,
            vector_top_k=global_settings.search_vector_top_k,
            rrf_k=global_settings.search_rrf_k,
            keyword_weight=global_settings.search_keyword_weight,
            vector_weight=global_settings.search_vector_weight,
            vector_min_score=global_settings.search_vector_min_score,
            keyword_field_weights=dict(DEFAULT_KEYWORD_FIELD_WEIGHTS),
            vector_field_weights=vector_weights,
            ocr_vector_field_weights=dict(DEFAULT_OCR_VECTOR_FIELD_WEIGHTS),
            enable_query_understanding=True,
            enable_structured_filters=False,
            enable_semantic_tag_boost=False,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_mode(mode: Optional[str]) -> SearchMode:
    if mode in ("keyword", "vector", "hybrid"):
        return mode  # type: ignore[return-value]
    return "hybrid"


def _normalise_vector_weights(weights: dict) -> dict[str, float]:
    """Clamp negatives to 0 and normalise so the total sums to 1.0."""
    cleaned = {k: max(0.0, float(v or 0.0)) for k, v in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return dict(DEFAULT_VECTOR_FIELD_WEIGHTS)
    return {k: v / total for k, v in cleaned.items()}
