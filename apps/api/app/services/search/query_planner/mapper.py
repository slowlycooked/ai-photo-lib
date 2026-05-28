"""Map validated LLM planner output to SearchQueryPlan."""
from __future__ import annotations

from typing import Any

from ...query_understanding_service import SearchQueryPlan
from .schema import LLMQueryPlannerOutput


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        value = str(term or "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(value)
    return deduped


def _fallback_exact_terms(query: str) -> list[str]:
    split_terms = [term for term in query.split() if term.strip()]
    if split_terms:
        return split_terms
    text = query.strip()
    return [text] if text else []


def merge_metadata_filters(primary: dict[str, Any], deterministic: dict[str, Any]) -> dict[str, Any]:
    """Merge deterministic metadata parser output into LLM output when missing."""
    merged = dict(primary)
    for key, value in deterministic.items():
        if key == "matched_metadata_terms":
            existing = merged.get("matched_metadata_terms") or []
            merged[key] = _dedupe_terms(list(existing) + list(value or []))
            continue
        existing = merged.get(key)
        if existing in (None, "", [], {}):
            merged[key] = value
    return merged


def planner_output_to_query_plan(
    *,
    query: str,
    output: LLMQueryPlannerOutput,
    planner_debug: dict,
    fallback_plan: SearchQueryPlan,
) -> SearchQueryPlan:
    exact_terms = _dedupe_terms(output.terms.exact) or _fallback_exact_terms(query)
    expanded_terms = _dedupe_terms(output.terms.expanded)
    support_terms = _dedupe_terms(output.terms.support)
    broad_terms = _dedupe_terms(output.terms.broad)
    negative_terms = _dedupe_terms(output.terms.negative)

    metadata_filters = merge_metadata_filters(
        output.metadata_filters.model_dump(),
        fallback_plan.metadata_filters or {},
    )

    raw_facets = output.facets.model_dump()
    intent_facets = {
        key: _dedupe_terms(list(values or []))
        for key, values in raw_facets.items()
        if values
    }

    matched_keys = _dedupe_terms(
        exact_terms
        + expanded_terms
        + list(output.concept_terms or [])
    )

    query_constraints = output.query_constraints.model_dump()
    if not query_constraints.get("query_core_facets"):
        query_constraints["query_core_facets"] = list(output.core_facets or [])

    return SearchQueryPlan(
        original_query=query,
        normalized_query=output.normalized_query.strip() or fallback_plan.normalized_query,
        semantic_query_text=(
            output.semantic_query_text.strip()
            or output.normalized_query.strip()
            or fallback_plan.semantic_query_text
            or query
        ),
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        broad_terms=broad_terms,
        support_terms=support_terms,
        negative_terms=negative_terms,
        intent_facets=intent_facets,
        query_constraints=query_constraints,
        semantic_tags=_dedupe_terms(list(output.semantic_tags or [])),
        intent=str(output.intent or fallback_plan.intent),
        search_mode=(
            output.search_mode
            if output.search_mode in ("keyword", "vector", "hybrid")
            else fallback_plan.search_mode
        ),
        filters=output.filters.model_dump(),
        recommended_profile=fallback_plan.recommended_profile,
        penalize_tags=fallback_plan.penalize_tags,
        matched_keys=matched_keys,
        concept_terms=_dedupe_terms(list(output.concept_terms or [])),
        core_facets=_dedupe_terms(list(output.core_facets or [])),
        core_facet_evidence=output.core_facet_evidence.model_dump(),
        metadata_filters=metadata_filters,
        planner_debug=planner_debug,
    )
