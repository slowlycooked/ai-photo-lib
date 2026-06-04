"""Map validated LLM planner output to SearchQueryPlan."""
from __future__ import annotations

from typing import Any

from ...query_understanding_service import SearchQueryPlan
from .schema import LLMQueryPlannerOutput

_ALLOWED_INTENTS = {
    "semantic_photo_search",
    "animal_search",
    "people_search",
    "group_photo_search",
    "food_search",
    "weather_search",
    "activity_search",
    "location_search",
    "ocr_text_search",
}

_INTENT_ALIASES = {
    "search": "semantic_photo_search",
    "semantic": "semantic_photo_search",
    "photo_search": "semantic_photo_search",
    "animal": "animal_search",
    "animals": "animal_search",
}

_ANIMAL_GUARDRAIL_TERMS = {
    "动物",
    "宠物",
    "野生动物",
    "小动物",
    "猫",
    "狗",
    "鸟",
    "鱼",
    "羊驼",
    "蛇",
    "animal",
    "animals",
}


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


def normalize_intent(raw_intent: Any, fallback_intent: str) -> str:
    intent = str(raw_intent or "").strip()
    if not intent:
        return fallback_intent
    normalized = _INTENT_ALIASES.get(intent, intent)
    if normalized not in _ALLOWED_INTENTS:
        return fallback_intent
    return normalized


def _merge_scalars_with_fallback(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged = dict(fallback)
    for key, value in primary.items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged


def _merge_list_terms(primary: list[str], fallback: list[str]) -> list[str]:
    return _dedupe_terms(list(primary or []) + list(fallback or []))


def _merge_core_facet_evidence(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    all_keys = set((fallback or {}).keys()) | set((primary or {}).keys())

    for key in all_keys:
        fallback_value = (fallback or {}).get(key)
        primary_value = (primary or {}).get(key)

        if isinstance(fallback_value, dict) or isinstance(primary_value, dict):
            fv = fallback_value if isinstance(fallback_value, dict) else {}
            pv = primary_value if isinstance(primary_value, dict) else {}
            child: dict[str, Any] = {}
            child_keys = set(fv.keys()) | set(pv.keys())
            for child_key in child_keys:
                fv_child = fv.get(child_key)
                pv_child = pv.get(child_key)
                if isinstance(fv_child, list) or isinstance(pv_child, list):
                    child[child_key] = _merge_list_terms(
                        list(pv_child or []),
                        list(fv_child or []),
                    )
                elif pv_child in (None, "", [], {}):
                    child[child_key] = fv_child
                else:
                    child[child_key] = pv_child
            merged[key] = child
            continue

        if isinstance(fallback_value, list) or isinstance(primary_value, list):
            merged[key] = _merge_list_terms(
                list(primary_value or []),
                list(fallback_value or []),
            )
            continue

        merged[key] = primary_value if primary_value not in (None, "", [], {}) else fallback_value

    return merged


def _apply_animal_guardrail(
    *,
    intent: str,
    filters: dict[str, Any],
    core_facets: list[str],
    matched_keys: list[str],
    exact_terms: list[str],
    expanded_terms: list[str],
    concept_terms: list[str],
) -> tuple[str, dict[str, Any], list[str]]:
    terms = {
        str(term).strip().lower()
        for term in (matched_keys + exact_terms + expanded_terms + concept_terms)
        if str(term).strip()
    }
    if not (terms & _ANIMAL_GUARDRAIL_TERMS):
        return intent, filters, core_facets

    enforced_filters = dict(filters)
    enforced_filters["has_animals"] = True
    enforced_facets = list(core_facets)
    if "object" not in enforced_facets:
        enforced_facets.append("object")
    return "animal_search", enforced_filters, enforced_facets


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
    # When LLM parsed successfully with adequate confidence, use LLM terms as the
    # primary source and do NOT merge fallback exact/expanded/support/broad terms.
    # This prevents the rule-engine's whole-sentence exact term (e.g. "去年张家口滑雪")
    # from polluting the keyword recall after the LLM has cleanly decomposed it into
    # semantic anchors (e.g. ["滑雪", "张家口"]).
    llm_parsed = bool(planner_debug.get("parsed"))
    llm_confidence = float(planner_debug.get("confidence") or 0.0)
    use_llm_terms = llm_parsed and llm_confidence >= 0.6
    llm_metadata_only = bool(output.metadata_filters.metadata_only)

    if use_llm_terms:
        llm_exact = _dedupe_terms(output.terms.exact)
        exact_terms = llm_exact if (llm_exact or llm_metadata_only) else _fallback_exact_terms(query)
        expanded_terms = _dedupe_terms(output.terms.expanded)
        support_terms = _dedupe_terms(output.terms.support)
        broad_terms = _dedupe_terms(output.terms.broad)
        # Negative terms are additive — always safe to merge both sources
        negative_terms = _merge_list_terms(_dedupe_terms(output.terms.negative), fallback_plan.negative_terms)
    else:
        exact_terms = _merge_list_terms(
            _dedupe_terms(output.terms.exact) or _fallback_exact_terms(query),
            fallback_plan.exact_terms,
        )
        expanded_terms = _merge_list_terms(_dedupe_terms(output.terms.expanded), fallback_plan.expanded_terms)
        support_terms = _merge_list_terms(_dedupe_terms(output.terms.support), fallback_plan.support_terms)
        broad_terms = _merge_list_terms(_dedupe_terms(output.terms.broad), fallback_plan.broad_terms)
        negative_terms = _merge_list_terms(_dedupe_terms(output.terms.negative), fallback_plan.negative_terms)

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

    llm_matched_keys = _dedupe_terms(
        exact_terms
        + expanded_terms
        + list(output.concept_terms or [])
    )
    matched_keys = (
        llm_matched_keys
        if use_llm_terms
        else _merge_list_terms(llm_matched_keys, fallback_plan.matched_keys)
    )

    query_constraints = _merge_scalars_with_fallback(
        output.query_constraints.model_dump(),
        fallback_plan.query_constraints or {},
    )
    if not query_constraints.get("query_core_facets"):
        query_constraints["query_core_facets"] = list(output.core_facets or [])

    intent = normalize_intent(output.intent, fallback_plan.intent)
    if (
        not use_llm_terms
        and intent == "semantic_photo_search"
        and fallback_plan.intent != "semantic_photo_search"
    ):
        intent = fallback_plan.intent

    filters = (
        output.filters.model_dump()
        if use_llm_terms
        else _merge_scalars_with_fallback(
            output.filters.model_dump(),
            fallback_plan.filters or {},
        )
    )
    core_facets = (
        _dedupe_terms(list(output.core_facets or []))
        if use_llm_terms
        else _merge_list_terms(
            _dedupe_terms(list(output.core_facets or [])),
            fallback_plan.core_facets,
        )
    )
    core_facet_evidence = (
        output.core_facet_evidence.model_dump()
        if use_llm_terms
        else _merge_core_facet_evidence(
            output.core_facet_evidence.model_dump(),
            fallback_plan.core_facet_evidence or {},
        )
    )

    intent, filters, core_facets = _apply_animal_guardrail(
        intent=intent,
        filters=filters,
        core_facets=core_facets,
        matched_keys=matched_keys,
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        concept_terms=list(output.concept_terms or []),
    )

    semantic_query_text = (
        ""
        if metadata_filters.get("metadata_only") is True
        else (
            output.semantic_query_text.strip()
            or output.normalized_query.strip()
            or fallback_plan.semantic_query_text
            or query
        )
    )

    return SearchQueryPlan(
        original_query=query,
        normalized_query=output.normalized_query.strip() or fallback_plan.normalized_query,
        semantic_query_text=semantic_query_text,
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        broad_terms=broad_terms,
        support_terms=support_terms,
        negative_terms=negative_terms,
        intent_facets=intent_facets,
        query_constraints=query_constraints,
        semantic_tags=(
            _dedupe_terms(list(output.semantic_tags or []))
            if use_llm_terms
            else _merge_list_terms(_dedupe_terms(list(output.semantic_tags or [])), fallback_plan.semantic_tags)
        ),
        intent=intent,
        search_mode=(
            output.search_mode
            if output.search_mode in ("keyword", "vector", "hybrid")
            else fallback_plan.search_mode
        ),
        filters=filters,
        recommended_profile=fallback_plan.recommended_profile,
        penalize_tags=fallback_plan.penalize_tags,
        matched_keys=matched_keys,
        concept_terms=(
            _dedupe_terms(list(output.concept_terms or []))
            if use_llm_terms
            else _merge_list_terms(_dedupe_terms(list(output.concept_terms or [])), fallback_plan.concept_terms)
        ),
        core_facets=core_facets,
        core_facet_evidence=core_facet_evidence,
        metadata_filters=metadata_filters,
        planner_debug=planner_debug,
    )
