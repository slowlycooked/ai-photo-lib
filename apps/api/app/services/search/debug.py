"""Debug payload builder for search."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from ..query_understanding_service import SearchQueryPlan
from .concept_recall import derive_concept_query_context
from .trace_writer import compact_filter_dict
from .types import EffectiveSearchSettings


def _latest_stage(trace: list[dict], stage: str) -> dict:
    return next(
        (event for event in reversed(trace) if event.get("stage") == stage),
        {},
    )


def build_timing_summary(trace: list[dict], planner_debug: Optional[dict] = None) -> dict:
    """Return stable, per-stage latency fields from the request trace."""
    stage_names = {
        "metadata_ms": "metadata_filter",
        "people_ms": "people_recall",
        "keyword_ms": "keyword_recall",
        "vector_ms": "vector_recall",
        "fusion_ms": "rrf_merge",
        "evidence_ms": "evidence_filter",
    }
    timings = {
        name: int(_latest_stage(trace, stage).get("duration_ms", 0) or 0)
        for name, stage in stage_names.items()
    }
    result_event = _latest_stage(trace, "result")
    timings.update(
        {
            "planner_ms": int((planner_debug or {}).get("latency_ms", 0) or 0),
            "hydration_ms": int(result_event.get("duration_ms", 0) or 0),
            "total_ms": int(result_event.get("total_ms", 0) or 0),
        }
    )
    return timings


@dataclass
class SearchDebugContext:
    query_plan: SearchQueryPlan
    settings: EffectiveSearchSettings
    trace: list
    embedding_dimension: int
    people_query_plan: Optional[dict] = None
    people_candidates: Optional[list] = None
    people_filter_mode: Optional[str] = None
    matched_person_ids: Optional[list[int]] = None
    metadata_filter_active: bool = False
    metadata_filter_skipped_reason: Optional[str] = None
    metadata_only_allowed: bool = True
    concept_terms: Optional[list[str]] = None
    concept_entity_terms: Optional[list[str]] = None
    concept_debug: Optional[dict] = None
    concept_candidates: int = 0
    people_visual_candidates: int = 0


def log_debug_payload(logger: logging.Logger, debug_payload: dict) -> None:
    """Emit a compact summary and the full debug payload for diagnostics."""
    try:
        logger.info(
            "[search][debug] intent=%s keyword_candidates=%s concept_candidates=%s vector_candidates=%s merged_candidates=%s filtered_candidates=%s stale_embedding_filtered=%s",
            debug_payload.get("intent"),
            debug_payload.get("keyword_candidates", 0),
            debug_payload.get("concept_candidates", 0),
            debug_payload.get("vector_candidates", 0),
            debug_payload.get("merged_candidates", 0),
            debug_payload.get("filtered_candidates", 0),
            debug_payload.get("stale_embedding_filtered", 0),
        )
        logger.debug("[search][debug] payload=%s", json.dumps(debug_payload, ensure_ascii=False, default=str))
    except Exception:
        logger.exception("[search][debug] failed to emit payload")


def build_logged_debug_payload(
    logger: logging.Logger,
    context: SearchDebugContext,
    *,
    mode: str,
    embedding_model: str = "",
    keyword_candidates: int = 0,
    vector_candidates: int = 0,
    merged_candidates: int = 0,
    fallback_reason: str = "",
    displayed_candidates: int = 0,
    filtered_candidates: int = 0,
    vector_only_rejected_count: int = 0,
    vector_only_reject_reasons: Optional[dict] = None,
    filtered_out_samples: Optional[list] = None,
    stale_embedding_filtered: int = 0,
    concept_candidates: Optional[int] = None,
    people_visual_candidates: Optional[int] = None,
    metadata_filters: Optional[dict] = None,
    metadata_candidates: int = 0,
    metadata_only: bool = False,
) -> dict:
    """Build and emit the debug payload from shared search debug context."""
    payload = build_debug_payload(
        query_plan=context.query_plan,
        mode=mode,
        embedding_model=embedding_model,
        embedding_dimension=context.embedding_dimension,
        keyword_candidates=keyword_candidates,
        concept_candidates=(
            context.concept_candidates
            if concept_candidates is None
            else concept_candidates
        ),
        people_visual_candidates=(
            context.people_visual_candidates
            if people_visual_candidates is None
            else people_visual_candidates
        ),
        vector_candidates=vector_candidates,
        merged_candidates=merged_candidates,
        fallback_reason=fallback_reason,
        settings=context.settings,
        trace=context.trace,
        displayed_candidates=displayed_candidates,
        filtered_candidates=filtered_candidates,
        vector_only_rejected_count=vector_only_rejected_count,
        vector_only_reject_reasons=vector_only_reject_reasons,
        filtered_out_samples=filtered_out_samples,
        stale_embedding_filtered=stale_embedding_filtered,
        metadata_filters=metadata_filters,
        metadata_candidates=metadata_candidates,
        metadata_only=metadata_only,
        people_query_plan=context.people_query_plan,
        people_candidates=context.people_candidates,
        people_filter_mode=context.people_filter_mode,
        matched_person_ids=context.matched_person_ids,
        metadata_filter_active=context.metadata_filter_active,
        metadata_filter_skipped_reason=context.metadata_filter_skipped_reason,
        metadata_only_allowed=context.metadata_only_allowed,
        concept_terms=context.concept_terms,
        concept_entity_terms=context.concept_entity_terms,
        concept_debug=context.concept_debug,
    )
    log_debug_payload(logger, payload)
    return payload


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
    vector_only_rejected_count: int = 0,
    vector_only_reject_reasons: Optional[dict] = None,
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
    trace_events = trace or []
    keyword_event = _latest_stage(trace_events, "keyword_recall")
    vector_event = _latest_stage(trace_events, "vector_recall")

    payload: dict = {
        "query_plan": {
            "planner_contract_version": getattr(query_plan, "planner_contract_version", "1"),
            "intent": query_plan.intent,
            "exact_terms": query_plan.exact_terms,
            "expanded_terms": query_plan.expanded_terms,
            "semantic_query_text": query_plan.semantic_query_text,
            "filter_clauses": query_plan.filter_clauses,
            "sort": query_plan.sort,
            "filters": getattr(query_plan, "planner_filters", {}) or {},
            "lexical": getattr(query_plan, "lexical_plan", {}) or {},
            "semantic": getattr(query_plan, "semantic_plan", {}) or {},
            "visual": getattr(query_plan, "visual_plan", {}) or {},
            "unresolved": getattr(query_plan, "unresolved_entities", {}) or {},
            "query_planner": query_plan.planner_debug,
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
        "filter_clauses": query_plan.filter_clauses,
        "sort": query_plan.sort,
        "core_facets": query_plan.core_facets,
        "query_planner": query_plan.planner_debug,
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
            "vector_only_rejected_count": vector_only_rejected_count,
            "vector_only_reject_reasons": vector_only_reject_reasons or {},
            "stale_embedding_filtered": stale_embedding_filtered,
        },
        "retrieval_queries": {
            "keyword_query_text": keyword_event.get("keyword_query_text", ""),
            "keyword_query_terms": keyword_event.get("keyword_query_terms", []),
            "vector_query_text": vector_event.get("vector_query_text", ""),
            "vector_query_source": vector_event.get("vector_query_source", "none"),
        },
        "resolved_constraints": {
            "metadata": compact_filter_dict(metadata_filters or query_plan.metadata_filters),
            "people": getattr(query_plan, "planner_filters", {}).get("people", []),
            "matched_person_ids": matched_person_ids or [],
        },
        "timings_ms": build_timing_summary(trace_events, query_plan.planner_debug),
        # Legacy flat counts kept for backward compat
        "keyword_candidates": keyword_candidates,
        "concept_candidates": concept_candidates,
        "people_visual_candidates": people_visual_candidates,
        "vector_candidates": vector_candidates,
        "merged_candidates": merged_candidates,
        "filtered_candidates": filtered_candidates,
        "vector_only_rejected_count": vector_only_rejected_count,
        "vector_only_reject_reasons": vector_only_reject_reasons or {},
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
            "entity_object_vector_only_min_score": settings.entity_object_vector_only_min_score,
            "entity_object_tag_min_score": settings.entity_object_tag_min_score,
            "entity_object_caption_min_score": settings.entity_object_caption_min_score,
            "animal_search_min_display_evidence_level": settings.animal_search_min_display_evidence_level,
            "keyword_field_weights": settings.keyword_field_weights,
            "vector_field_weights": settings.vector_field_weights,
            "ocr_vector_field_weights": settings.ocr_vector_field_weights,
            "enable_query_understanding": settings.enable_query_understanding,
            "enable_structured_filters": settings.enable_structured_filters,
            "enable_semantic_tag_boost": settings.enable_semantic_tag_boost,
        },
        "trace": trace_events,
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
