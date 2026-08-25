"""Map validated LLM planner output to SearchQueryPlan."""
from __future__ import annotations

import re
from typing import Any

from ...query_understanding_service import SearchQueryPlan
from .schema import LLMQueryPlannerOutput, QueryPlanV2

_ALLOWED_INTENTS = {
    "semantic_photo_search",
    "metadata_location_search",
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
    "location-based_photo_search": "metadata_location_search",
    "location_based_photo_search": "metadata_location_search",
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

_NON_ENTITY_PEOPLE_TERMS = {
    "班级",
    "班集体",
    "全班",
    "同学",
    "同学们",
    "多人",
    "人群",
    "集体",
    "团体",
    "朋友们",
}

_PEOPLE_COUNT_CONTROL_RE = re.compile(
    r"人数\s*(?:大于|超过|不少于|至少|大于等于|小于|少于|不超过|至多|小于等于|等于|为|是)\s*\d+"
    r"|(?:至少|不少于|超过|少于|不超过|至多|正好|恰好|大于|小于|大于等于|小于等于)\s*\d+\s*人(?:的)?"
    r"|\d+\s*人(?:以上|以下)(?:的)?"
)
_PHOTO_TERM_SUFFIX_RE = re.compile(r"(?:的)?(?:照片|图片|相片)$")


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


def _strip_people_count_controls(
    terms: list[str],
    filter_clauses: list[dict],
) -> list[str]:
    if not any(clause.get("field") == "people_count" for clause in filter_clauses):
        return _dedupe_terms(terms)

    residual_terms: list[str] = []
    for term in terms:
        residual = _PEOPLE_COUNT_CONTROL_RE.sub(" ", str(term or ""))
        residual = _PHOTO_TERM_SUFFIX_RE.sub("", residual.strip())
        residual = residual.strip(" 的,，;；")
        if residual:
            residual_terms.append(residual)
    return _dedupe_terms(residual_terms)


def _is_non_entity_people_term(value: str) -> bool:
    return str(value or "").strip().lower() in _NON_ENTITY_PEOPLE_TERMS


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


def _merge_control_dicts(primary: list[dict], fallback: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in list(primary or []) + list(fallback or []):
        value = dict(item or {})
        key = (
            str(value.get("field") or ""),
            str(value.get("operator") or value.get("order") or ""),
            repr(value.get("value")),
        )
        if not key[0] or key in seen:
            continue
        seen.add(key)
        merged.append(value)
    return merged


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
        if (
            metadata_filters.get("metadata_only") is True
            or intent == "metadata_location_search"
        )
        else (
            output.semantic_query_text.strip()
            or output.normalized_query.strip()
            or fallback_plan.semantic_query_text
            or query
        )
    )

    filter_clauses = _merge_control_dicts(
        [item.model_dump() for item in output.filter_clauses],
        fallback_plan.filter_clauses,
    )
    sort_specs = _merge_control_dicts(
        [item.model_dump() for item in output.sort],
        fallback_plan.sort,
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
        filter_clauses=filter_clauses,
        sort=sort_specs,
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


def planner_v2_output_to_query_plan(
    *,
    query: str,
    output: QueryPlanV2,
    planner_debug: dict,
    deterministic_plan: SearchQueryPlan,
) -> SearchQueryPlan:
    """Adapt QueryPlan V2 to the existing search execution contract.

    Only deterministic factual metadata is backfilled. Semantic terms, visual
    meaning, intent and evidence policy are derived from V2 without consulting
    the legacy rule planner.
    """
    filter_clauses = _merge_control_dicts(
        [item.model_dump() for item in output.filter_clauses],
        deterministic_plan.filter_clauses,
    )
    sort_specs = _merge_control_dicts(
        [item.model_dump() for item in output.ranking.sort],
        deterministic_plan.sort,
    )
    lexical_required = _strip_people_count_controls(
        output.lexical.required,
        filter_clauses,
    )
    lexical_preferred = _strip_people_count_controls(
        output.lexical.preferred,
        filter_clauses,
    )
    lexical_excluded = _dedupe_terms(output.lexical.excluded)
    semantic_concepts = _dedupe_terms(output.semantic.concepts)
    semantic_queries = _strip_people_count_controls(
        output.semantic.queries,
        filter_clauses,
    )
    visual_objects = _dedupe_terms(output.visual.objects)
    visual_scenes = _dedupe_terms(output.visual.scenes)
    visual_activities = _dedupe_terms(output.visual.activities)
    visual_attributes = _dedupe_terms(output.visual.attributes)
    visual_terms = _dedupe_terms(
        visual_objects + visual_scenes + visual_activities + visual_attributes
    )

    deterministic_metadata = deterministic_plan.metadata_filters or {}
    deterministic_metadata_only = bool(
        deterministic_metadata.get("metadata_only")
    )
    entity_people = [
        item
        for item in output.filters.people
        if not _is_non_entity_people_term(item.name)
    ]
    generic_people_terms = _dedupe_terms(
        [
            item.name
            for item in output.filters.people
            if _is_non_entity_people_term(item.name)
        ]
    )
    unresolved_entities = output.unresolved.model_dump()
    unresolved_entities["people"] = [
        name
        for name in unresolved_entities.get("people", [])
        if not _is_non_entity_people_term(name)
    ]
    low_confidence = float(output.confidence or 0.0) < 0.6
    if deterministic_metadata_only:
        lexical_required = []
        lexical_preferred = []
        lexical_excluded = []
        semantic_concepts = []
        semantic_queries = []
        visual_objects = []
        visual_scenes = []
        visual_activities = []
        visual_attributes = []
        visual_terms = []
    elif low_confidence:
        lexical_required = []
        lexical_preferred = _strip_people_count_controls(
            _fallback_exact_terms(query),
            filter_clauses,
        )
        semantic_concepts = []
        semantic_queries = _strip_people_count_controls(
            _fallback_exact_terms(query),
            filter_clauses,
        )
        visual_objects = []
        visual_scenes = []
        visual_activities = []
        visual_attributes = []
        visual_terms = []
    else:
        semantic_concepts = _merge_list_terms(
            semantic_concepts,
            generic_people_terms,
        )
        semantic_queries = _merge_list_terms(
            semantic_queries,
            generic_people_terms,
        )

    planner_filters = output.filters.model_dump()
    planner_filters["people"] = [item.model_dump() for item in entity_people]
    required_time_ranges = [item for item in output.filters.time_ranges]
    deterministic_date_from = deterministic_metadata.get("date_from")
    deterministic_date_to = deterministic_metadata.get("date_to")
    if (
        len(required_time_ranges) == 1
        and deterministic_date_from
        and deterministic_date_to
    ):
        planner_filters["time_ranges"] = [
            {
                "start": deterministic_date_from,
                "end": deterministic_date_to,
            }
        ]
    required_locations = [item for item in output.filters.locations if item.required]
    required_cameras = [item for item in output.filters.camera if item.required]

    metadata_seed: dict[str, Any] = {
        "place_terms": _dedupe_terms([item.name for item in required_locations]),
        "has_gps": output.filters.has_gps,
        "matched_metadata_terms": _dedupe_terms(
            [item.name for item in required_locations]
            + [item.make or "" for item in required_cameras]
            + [item.model_contains or "" for item in required_cameras]
        ),
    }
    if required_time_ranges:
        metadata_seed["date_from"] = required_time_ranges[0].start
        metadata_seed["date_to"] = required_time_ranges[0].end
    if required_cameras:
        camera = required_cameras[0]
        metadata_seed["camera_make"] = camera.make
        metadata_seed["camera_model"] = camera.model_contains

    has_semantic_residual = bool(
        lexical_required
        or lexical_preferred
        or semantic_concepts
        or semantic_queries
        or visual_terms
    )
    has_factual_constraints = bool(
        required_time_ranges
        or required_locations
        or required_cameras
        or entity_people
        or output.filters.has_gps is not None
        or output.filters.media_types
        or output.filters.albums
        or filter_clauses
    )
    metadata_seed["metadata_only"] = bool(
        has_factual_constraints and not has_semantic_residual
    )
    metadata_filters = merge_metadata_filters(
        metadata_seed,
        deterministic_metadata,
    )
    for key in ("date_from", "date_to", "year", "month", "months"):
        deterministic_value = deterministic_metadata.get(key)
        if deterministic_value not in (None, "", [], {}):
            metadata_filters[key] = deterministic_value

    semantic_query_text = " ".join(semantic_queries).strip()
    semantic_source = (
        "metadata_only"
        if deterministic_metadata_only
        else ("raw_query_fallback" if low_confidence else "qwen")
    )
    if not semantic_query_text and not metadata_filters.get("metadata_only"):
        semantic_query_text = query.strip()
        semantic_source = "raw_query_fallback"

    intent_facets = {
        key: values
        for key, values in {
            "object": visual_objects,
            "scene": visual_scenes,
            "activity": visual_activities,
            "attribute": visual_attributes,
        }.items()
        if values
    }
    query_constraints = {
        "requires_visual_evidence": has_semantic_residual,
        "allow_weak_only_match": False,
        "allow_vector_only_match": True,
        "min_evidence_level": "C",
        "query_core_facets": [],
        "requires_metadata_evidence": has_factual_constraints,
    }
    effective_lexical_plan = {
        "required": lexical_required,
        "preferred": lexical_preferred,
        "excluded": lexical_excluded,
    }
    effective_semantic_plan = {
        "concepts": semantic_concepts,
        "queries": semantic_queries,
    }
    effective_visual_plan = {
        "objects": visual_objects,
        "scenes": visual_scenes,
        "activities": visual_activities,
        "attributes": visual_attributes,
    }

    debug = dict(planner_debug)
    debug.update(
        {
            "planner_contract_version": "2",
            "semantic_source": semantic_source,
            "semantic_fallback_reason": (
                ""
                if deterministic_metadata_only
                else ("low_confidence" if low_confidence else "")
            ),
            "semantic_queries": semantic_queries,
            "filters": planner_filters,
            "filter_clauses": filter_clauses,
            "sort": sort_specs,
            "lexical": effective_lexical_plan,
            "semantic": effective_semantic_plan,
            "visual": effective_visual_plan,
            "unresolved": unresolved_entities,
        }
    )

    return SearchQueryPlan(
        original_query=query,
        normalized_query=query.strip(),
        semantic_query_text=semantic_query_text,
        exact_terms=lexical_required,
        expanded_terms=lexical_preferred,
        support_terms=visual_terms,
        broad_terms=semantic_concepts,
        negative_terms=lexical_excluded,
        intent_facets=intent_facets,
        query_constraints=query_constraints,
        semantic_tags=_dedupe_terms(semantic_concepts + visual_terms),
        intent=("ocr_text_search" if output.intent == "ocr_search" else "semantic_photo_search"),
        search_mode="hybrid",
        filters={},
        filter_clauses=filter_clauses,
        sort=sort_specs,
        recommended_profile=(
            "ocr_text" if output.intent == "ocr_search" else "default_semantic"
        ),
        penalize_tags=[],
        matched_keys=_dedupe_terms(lexical_required + lexical_preferred),
        concept_terms=semantic_concepts,
        core_facets=[],
        core_facet_evidence={},
        metadata_filters=metadata_filters,
        planner_debug=debug,
        planner_contract_version="2",
        planner_filters=planner_filters,
        lexical_plan=effective_lexical_plan,
        semantic_plan=effective_semantic_plan,
        visual_plan=effective_visual_plan,
        unresolved_entities=unresolved_entities,
    )
