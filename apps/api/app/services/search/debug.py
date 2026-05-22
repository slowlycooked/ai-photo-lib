"""Debug payload builder for search."""
from __future__ import annotations

from ..query_understanding_service import SearchQueryPlan
from .settings_resolver import SearchSettingsResolver
from .types import EffectiveSearchSettings


def build_debug_payload(
    *,
    query_plan: SearchQueryPlan,
    mode: str,
    embedding_model: str,
    embedding_dimension: int,
    keyword_candidates: int,
    vector_candidates: int,
    merged_candidates: int,
    fallback_reason: str,
    settings: EffectiveSearchSettings,
) -> dict:
    """Build the debug payload that accompanies a search response."""
    payload: dict = {
        "original_query": query_plan.original_query,
        "normalized_query": query_plan.normalized_query,
        # Three-tier terms
        "exact_terms": query_plan.exact_terms,
        "expanded_terms": query_plan.expanded_terms,
        "broad_terms": query_plan.broad_terms,
        # Legacy field kept for backward compatibility
        "intent": query_plan.intent,
        "recommended_profile": query_plan.recommended_profile,
        "mode": mode,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "keyword_candidates": keyword_candidates,
        "vector_candidates": vector_candidates,
        "merged_candidates": merged_candidates,
        # Effective settings snapshot (for tuning visibility)
        "settings_snapshot": {
            "default_mode": settings.default_mode,
            "keyword_top_k": settings.keyword_top_k,
            "vector_top_k": settings.vector_top_k,
            "rrf_k": settings.rrf_k,
            "keyword_weight": settings.keyword_weight,
            "vector_weight": settings.vector_weight,
            "vector_min_score": settings.vector_min_score,
            "keyword_field_weights": settings.keyword_field_weights,
            "vector_field_weights": settings.vector_field_weights,
            "ocr_vector_field_weights": settings.ocr_vector_field_weights,
            "enable_query_understanding": settings.enable_query_understanding,
            "enable_structured_filters": settings.enable_structured_filters,
            "enable_semantic_tag_boost": settings.enable_semantic_tag_boost,
        },
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload
