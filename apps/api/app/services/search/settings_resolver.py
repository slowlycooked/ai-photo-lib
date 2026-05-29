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
from ..project_query_planner_settings_service import resolve_query_planner_settings
from ..query_understanding_rule_packs import DEFAULT_BASE_PACK_ID, normalise_extension_pack_ids
from .types import (
    DEFAULT_KEYWORD_FIELD_WEIGHTS,
    DEFAULT_OCR_VECTOR_FIELD_WEIGHTS,
    DEFAULT_VECTOR_FIELD_WEIGHTS,
    EffectiveSearchSettings,
    SearchMode,
)

logger = logging.getLogger(__name__)


def _normalise_concept_taxonomy(raw: object) -> list[dict]:
    """Return a sanitized project concept taxonomy list.

    Each entry keeps only known keys and ensures list-valued properties.
    Unknown or malformed entries are ignored.
    """
    if not isinstance(raw, list):
        return []

    normalized: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        concept = str(item.get("concept") or "").strip()
        if not concept:
            continue
        normalized.append(
            {
                "concept": concept,
                "children": [
                    str(v).strip()
                    for v in (item.get("children") or [])
                    if str(v).strip()
                ],
                "child_negative_contexts": [
                    str(v).strip()
                    for v in (item.get("child_negative_contexts") or [])
                    if str(v).strip()
                ],
                "aliases": [
                    str(v).strip()
                    for v in (item.get("aliases") or [])
                    if str(v).strip()
                ],
                "positive_fields": [
                    str(v).strip()
                    for v in (item.get("positive_fields") or [])
                    if str(v).strip()
                ],
                "negative_terms": [
                    str(v).strip()
                    for v in (item.get("negative_terms") or [])
                    if str(v).strip()
                ],
                "recall_policy": str(item.get("recall_policy") or "").strip(),
                "evidence_policy": str(item.get("evidence_policy") or "").strip(),
            }
        )
    return normalized


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
            enable_semantic_tag_boost=False,
            entity_object_vector_only_min_score=0.62,
            entity_object_tag_min_score=0.62,
            entity_object_caption_min_score=0.58,
            animal_search_min_display_evidence_level="B",
            concept_taxonomy=[],
            query_understanding_base_pack=DEFAULT_BASE_PACK_ID,
            query_understanding_extension_packs=[],
            query_planner_enabled=True,
            query_planner_provider="llama-server",
            query_planner_endpoint_url=global_settings.query_planner_base_url,
            query_planner_api_key="",
            query_planner_model_name=global_settings.query_planner_alias,
            query_planner_temperature=0.0,
            query_planner_top_p=0.1,
            query_planner_max_tokens=220,
            query_planner_timeout_seconds=20,
            query_planner_json_parse_strategy="strict_json_then_extract",
            query_planner_planner_version="llm_query_planner_v1",
            query_planner_prompt_template="",
            query_planner_system_prompt="",
            query_planner_fallback_mode="rule_fallback",
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
            query_planner_settings = resolve_query_planner_settings(
                db,
                project_id,
                search_quality_settings=_q,
            )
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
                require_core_facet_match=bool(_q.get("require_core_facet_match", False)),
                allow_vector_only_for_facet_query=bool(_q.get("allow_vector_only_for_facet_query", True)),
                entity_object_vector_only_min_score=float(
                    _q.get("entity_object_vector_only_min_score", 0.62)
                ),
                entity_object_tag_min_score=float(_q.get("entity_object_tag_min_score", 0.62)),
                entity_object_caption_min_score=float(
                    _q.get("entity_object_caption_min_score", 0.58)
                ),
                animal_search_min_display_evidence_level=str(
                    _q.get("animal_search_min_display_evidence_level", "B")
                ),
                concept_taxonomy=_normalise_concept_taxonomy(_q.get("concept_taxonomy")),
                query_understanding_base_pack=str(
                    _q.get("query_understanding_base_pack") or DEFAULT_BASE_PACK_ID
                ).strip(),
                query_understanding_extension_packs=list(
                    normalise_extension_pack_ids(
                        _q.get("query_understanding_extension_packs")
                    )
                ),
                query_planner_enabled=bool(query_planner_settings["enabled"]),
                query_planner_provider=str(query_planner_settings["provider"]),
                query_planner_endpoint_url=str(query_planner_settings["endpoint_url"]),
                query_planner_api_key=str(query_planner_settings["api_key"]),
                query_planner_model_name=str(query_planner_settings["model_name"]),
                query_planner_temperature=float(query_planner_settings["temperature"]),
                query_planner_top_p=float(query_planner_settings["top_p"]),
                query_planner_max_tokens=int(query_planner_settings["max_tokens"]),
                query_planner_timeout_seconds=int(query_planner_settings["timeout_seconds"]),
                query_planner_json_parse_strategy=str(query_planner_settings["json_parse_strategy"]),
                query_planner_planner_version=str(query_planner_settings["planner_version"]),
                query_planner_prompt_template=str(query_planner_settings["prompt_template"]),
                query_planner_system_prompt=str(query_planner_settings["system_prompt"]),
                query_planner_fallback_mode=str(query_planner_settings["fallback_mode"]),
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
        query_planner_settings = resolve_query_planner_settings(
            db,
            project_id,
            search_quality_settings=None,
        )

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
            concept_taxonomy=[],
            query_understanding_base_pack=DEFAULT_BASE_PACK_ID,
            query_understanding_extension_packs=[],
            query_planner_enabled=bool(query_planner_settings["enabled"]),
            query_planner_provider=str(query_planner_settings["provider"]),
            query_planner_endpoint_url=str(query_planner_settings["endpoint_url"]),
            query_planner_api_key=str(query_planner_settings["api_key"]),
            query_planner_model_name=str(query_planner_settings["model_name"]),
            query_planner_temperature=float(query_planner_settings["temperature"]),
            query_planner_top_p=float(query_planner_settings["top_p"]),
            query_planner_max_tokens=int(query_planner_settings["max_tokens"]),
            query_planner_timeout_seconds=int(query_planner_settings["timeout_seconds"]),
            query_planner_json_parse_strategy=str(query_planner_settings["json_parse_strategy"]),
            query_planner_planner_version=str(query_planner_settings["planner_version"]),
            query_planner_prompt_template=str(query_planner_settings["prompt_template"]),
            query_planner_system_prompt=str(query_planner_settings["system_prompt"]),
            query_planner_fallback_mode=str(query_planner_settings["fallback_mode"]),
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
