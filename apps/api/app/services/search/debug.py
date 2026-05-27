"""Debug payload builder for search."""
from __future__ import annotations

from typing import Optional

from ..query_understanding_service import SearchQueryPlan
from .concept_recall import derive_concept_query_context
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
    filtered_out_samples: Optional[list] = None,
    stale_embedding_filtered: int = 0,
    concept_candidates: int = 0,
    people_visual_candidates: int = 0,
    metadata_filters: Optional[dict] = None,
    metadata_candidates: int = 0,
    metadata_only: bool = False,
    people_query_plan: Optional[dict] = None,
    people_candidates: Optional[list] = None,
    people_filter_mode: Optional[str] = None,
    matched_person_ids: Optional[list[int]] = None,
    metadata_filter_active: bool = False,
    metadata_filter_skipped_reason: Optional[str] = None,
    metadata_only_allowed: bool = True,
    concept_terms: Optional[list[str]] = None,
    concept_entity_terms: Optional[list[str]] = None,
    concept_debug: Optional[dict] = None,
) -> dict:
    """Build the debug payload that accompanies a search response."""
    derived_concept_terms, derived_entity_terms, derived_concept_facets = derive_concept_query_context(query_plan)
    payload_concept_terms = concept_terms if concept_terms is not None else derived_concept_terms
    payload_entity_terms = (
        concept_entity_terms if concept_entity_terms is not None else derived_entity_terms
    )

    payload: dict = {
        "query_plan": {
            "intent": query_plan.intent,
            "exact_terms": query_plan.exact_terms,
            "expanded_terms": query_plan.expanded_terms,
            "semantic_query_text": query_plan.semantic_query_text,
        },
        "original_query": query_plan.original_query,
        "normalized_query": query_plan.normalized_query,
        "semantic_query_text": query_plan.semantic_query_text,
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
        "matched_keys": query_plan.matched_keys,
        "query_constraints": query_plan.query_constraints,
        "core_facets": query_plan.core_facets,
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
            "concept_candidates": concept_candidates,
            "people_visual_candidates": people_visual_candidates,
            "vector_candidates": vector_candidates,
            "merged_candidates": merged_candidates,
            "displayed_candidates": displayed_candidates,
            "filtered_candidates": filtered_candidates,
            "stale_embedding_filtered": stale_embedding_filtered,
        },
        # Legacy flat counts kept for backward compat
        "keyword_candidates": keyword_candidates,
        "concept_candidates": concept_candidates,
        "people_visual_candidates": people_visual_candidates,
        "vector_candidates": vector_candidates,
        "merged_candidates": merged_candidates,
        "filtered_candidates": filtered_candidates,
        "stale_embedding_filtered": stale_embedding_filtered,
        "metadata_filter_active": metadata_filter_active,
        "metadata_filter_skipped_reason": metadata_filter_skipped_reason,
        "metadata_only_allowed": metadata_only_allowed,
        "concept_terms": payload_concept_terms,
        "concept_entity_terms": payload_entity_terms,
        "concept_debug": concept_debug or {
            "enabled": True,
            "reason": "connected",
            "concept_terms": payload_concept_terms,
            "concept_facets": derived_concept_facets,
            "entity_terms": payload_entity_terms,
            "candidates": concept_candidates,
            "top_scores": [],
        },
        # Evidence / filter stats
        "filter_stats": {
            "filtered_count": filtered_candidates,
            "stale_embedding_filtered": stale_embedding_filtered,
        },
        # Sample of filtered-out candidates for debugging
        "filtered_out_samples": filtered_out_samples or [],
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
    if metadata_filters:
        payload["metadata_filters"] = {
            k: v for k, v in metadata_filters.items()
            if v not in (None, [], False, {})
        }
        payload["metadata_candidates"] = metadata_candidates
        payload["metadata_only"] = metadata_only
        payload["matched_metadata_terms"] = metadata_filters.get("matched_metadata_terms", [])
    if people_query_plan is not None:
        payload["people_query_plan"] = people_query_plan
    if people_candidates is not None:
        payload["people_candidates"] = people_candidates
    if people_filter_mode is not None:
        payload["people_filter_mode"] = people_filter_mode
    if matched_person_ids is not None:
        payload["matched_person_ids"] = matched_person_ids
    return payload
