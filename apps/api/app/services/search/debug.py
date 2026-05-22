"""Debug payload builder for search."""
from __future__ import annotations

from typing import Optional

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
    trace: Optional[list] = None,
    displayed_candidates: int = 0,
    filtered_candidates: int = 0,
) -> dict:
    """Build the debug payload that accompanies a search response."""
    payload: dict = {
        "original_query": query_plan.original_query,
        "normalized_query": query_plan.normalized_query,
        "query_profile": query_plan.intent,
        # Five-tier term breakdown
        "term_groups": {
            "must": query_plan.exact_terms,
            "strong": query_plan.expanded_terms,
            "support": query_plan.support_terms,
            "weak": query_plan.broad_terms,
            "negative": query_plan.negative_terms,
        },
        # Legacy flat fields kept for backward compatibility
        "exact_terms": query_plan.exact_terms,
        "expanded_terms": query_plan.expanded_terms,
        "broad_terms": query_plan.broad_terms,
        # Facet metadata
        "intent_facets": query_plan.intent_facets,
        "query_constraints": query_plan.query_constraints,
        # Penalise tags snapshot
        "penalize_tags": query_plan.penalize_tags,
        "intent": query_plan.intent,
        "recommended_profile": query_plan.recommended_profile,
        "mode": mode,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        # Candidate pipeline counts
        "candidate_counts": {
            "keyword_candidates": keyword_candidates,
            "vector_candidates": vector_candidates,
            "merged_candidates": merged_candidates,
            "displayed_candidates": displayed_candidates,
            "filtered_candidates": filtered_candidates,
        },
        # Legacy flat counts kept for backward compat
        "keyword_candidates": keyword_candidates,
        "vector_candidates": vector_candidates,
        "merged_candidates": merged_candidates,
        # Effective settings snapshot
        "settings_snapshot": {
            "default_mode": settings.default_mode,
            "keyword_top_k": settings.keyword_top_k,
            "vector_top_k": settings.vector_top_k,
            "rrf_k": settings.rrf_k,
            "keyword_weight": settings.keyword_weight,
            "vector_weight": settings.vector_weight,
            "vector_min_score": settings.vector_min_score,
            "vector_strict_score": settings.vector_strict_score,
            "min_display_evidence_level": settings.min_display_evidence_level,
            "enable_evidence_filter": settings.enable_evidence_filter,
            "enable_negative_penalty": settings.enable_negative_penalty,
            "evidence_weight": settings.evidence_weight,
            "negative_term_penalty": settings.negative_term_penalty,
            "keyword_field_weights": settings.keyword_field_weights,
            "vector_field_weights": settings.vector_field_weights,
            "ocr_vector_field_weights": settings.ocr_vector_field_weights,
            "enable_query_understanding": settings.enable_query_understanding,
            "enable_structured_filters": settings.enable_structured_filters,
            "enable_semantic_tag_boost": settings.enable_semantic_tag_boost,
        },
        "trace": trace or [],
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload
