"""Search query understanding boundary."""
from __future__ import annotations

from typing import Optional

from ..query_understanding_service import SearchQueryPlan, understand_query as default_understand_query
from .query_planner import resolve_query_plan_llm_first
from .types import EffectiveSearchSettings


def resolve_search_query_plan(
    query: str,
    *,
    project_id: Optional[int],
    settings: EffectiveSearchSettings,
    understander=default_understand_query,
    planner_resolver=resolve_query_plan_llm_first,
) -> SearchQueryPlan:
    """Resolve a query plan while honoring per-project search settings."""
    if settings.enable_query_understanding:
        return planner_resolver(
            query,
            project_id=project_id,
            settings=settings,
            understander=understander,
        )

    return SearchQueryPlan(
        original_query=query,
        normalized_query=query,
        exact_terms=[word for word in query.split() if word],
        intent="semantic_photo_search",
        planner_debug={
            "enabled": False,
            "used_fallback": True,
            "fallback_reason": "query_understanding_disabled",
        },
    )


def build_query_plan_trace_event(
    query_plan: SearchQueryPlan,
    *,
    stage: str = "query_plan",
    include_recommended_profile: bool = True,
) -> dict:
    """Build the trace event emitted after query understanding."""
    event = {
        "stage": stage,
        "query": query_plan.original_query,
        "intent": query_plan.intent,
        "normalized_query": query_plan.normalized_query,
        "semantic_query_text": query_plan.semantic_query_text,
        "exact_terms": query_plan.exact_terms,
        "expanded_terms": query_plan.expanded_terms,
        "broad_terms": query_plan.broad_terms,
        "support_terms": query_plan.support_terms,
        "negative_terms": query_plan.negative_terms,
        "matched_keys": query_plan.matched_keys,
        "core_facets": query_plan.core_facets,
    }
    if include_recommended_profile:
        event["recommended_profile"] = query_plan.recommended_profile
    if query_plan.planner_debug:
        event["query_planner"] = query_plan.planner_debug
    return event
