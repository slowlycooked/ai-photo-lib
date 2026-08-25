"""Fallback helpers for query planner failures."""
from __future__ import annotations

from typing import Callable, Optional

from ...query_understanding_service import SearchQueryPlan


def build_fallback_plan(
    *,
    query: str,
    project_id: Optional[int],
    understander: Callable,
    concept_taxonomy: list[dict],
    rule_base_pack_id: str,
    rule_extension_pack_ids: list[str],
    planner_debug: dict,
) -> SearchQueryPlan:
    plan = understander(
        query,
        project_id=project_id,
        concept_taxonomy=concept_taxonomy,
        rule_base_pack_id=rule_base_pack_id,
        rule_extension_pack_ids=rule_extension_pack_ids,
    )
    plan.planner_debug = dict(planner_debug)
    return plan


def build_fallback_plan_v2(
    *,
    query: str,
    project_id: Optional[int],
    understander: Callable,
    rule_base_pack_id: str,
    rule_extension_pack_ids: list[str],
    planner_debug: dict,
) -> SearchQueryPlan:
    """Build a V2 fallback using only deterministic factual parse results."""
    deterministic = understander(
        query,
        project_id=project_id,
        concept_taxonomy=[],
        rule_base_pack_id=rule_base_pack_id,
        rule_extension_pack_ids=rule_extension_pack_ids,
    )
    metadata_filters = dict(deterministic.metadata_filters or {})
    # The legacy normalized_query may already contain taxonomy/synonym
    # expansion. V2 fallback deliberately keeps only raw normalization.
    normalized_query = str(query or "").strip()
    metadata_only = bool(metadata_filters.get("metadata_only"))
    semantic_query_text = "" if metadata_only else normalized_query
    preferred_terms = [normalized_query] if normalized_query else []
    debug = dict(planner_debug)
    debug.update(
        {
            "planner_contract_version": "2",
            "semantic_source": (
                "metadata_only" if metadata_only else "raw_query_fallback"
            ),
            "semantic_queries": (
                [] if metadata_only or not normalized_query else [normalized_query]
            ),
        }
    )

    return SearchQueryPlan(
        original_query=query,
        normalized_query=normalized_query,
        semantic_query_text=semantic_query_text,
        exact_terms=[],
        expanded_terms=preferred_terms,
        broad_terms=[],
        support_terms=[],
        negative_terms=[],
        intent="semantic_photo_search",
        search_mode="hybrid",
        query_constraints={
            "requires_visual_evidence": not metadata_only,
            "allow_weak_only_match": False,
            "allow_vector_only_match": not metadata_only,
            "min_evidence_level": "C",
            "query_core_facets": [],
            "requires_metadata_evidence": bool(metadata_filters),
        },
        metadata_filters=metadata_filters,
        planner_debug=debug,
        planner_contract_version="2",
        lexical_plan={
            "required": [],
            "preferred": preferred_terms,
            "excluded": [],
        },
        semantic_plan={
            "concepts": [],
            "queries": ([] if metadata_only else preferred_terms),
        },
        visual_plan={
            "objects": [],
            "scenes": [],
            "activities": [],
            "attributes": [],
        },
    )
