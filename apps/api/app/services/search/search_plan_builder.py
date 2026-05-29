"""Build search execution plans from query understanding and runtime inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..query_understanding_service import understand_query
from .people_query_resolver import PeopleQueryResolution, resolve_people_query
from .query_understanding import resolve_search_query_plan
from .settings_resolver import SearchSettingsResolver
from .types import EffectiveSearchSettings, SearchMode

_METADATA_ONLY_BLOCKED_INTENTS: frozenset[str] = frozenset({
    "animal_search",
    "people_search",
    "group_photo_search",
    "food_search",
    "weather_search",
    "activity_search",
})

_TEMPORAL_METADATA_KEYS: tuple[str, ...] = (
    "year",
    "month",
    "months",
    "season",
    "date_from",
    "date_to",
)


@dataclass(frozen=True)
class SearchPlan:
    effective_settings: EffectiveSearchSettings
    query_plan: object
    search_query_plan: object
    people_resolution: PeopleQueryResolution
    people_query_plan: dict
    effective_mode: SearchMode
    metadata_filters: dict
    metadata_filter_active: bool
    metadata_only_requested: bool
    metadata_only_allowed: bool
    metadata_filter_skipped_reason: str


def build_search_plan(
    db: Session,
    *,
    query: str,
    mode: SearchMode,
    project_id: Optional[int],
    face_filter_active: bool,
    settings_resolver_cls=SearchSettingsResolver,
    query_plan_resolver=resolve_search_query_plan,
    understander=understand_query,
    people_query_resolver=resolve_people_query,
    people_resolution_cls=PeopleQueryResolution,
) -> SearchPlan:
    """Build the search plan used by recall/fusion stages."""
    if project_id is not None:
        effective_settings = settings_resolver_cls.resolve(db, project_id)
    else:
        effective_settings = settings_resolver_cls.defaults()

    query_plan = query_plan_resolver(
        query,
        project_id=project_id,
        settings=effective_settings,
        understander=understander,
    )

    if project_id is not None:
        people_resolution = people_query_resolver(
            db,
            project_id=project_id,
            query=query,
            query_plan=query_plan,
        )
    else:
        people_resolution = people_resolution_cls(
            query=query,
            residual_query=query,
            people_filter_mode="none",
            matched_people=[],
        )

    people_query_plan: dict = {
        "query": query,
        "residual_query": people_resolution.residual_query,
        "is_people_only": people_resolution.is_people_only,
        "matched_people": [
            {
                "person_id": p.person_id,
                "display_name": p.display_name,
                "normalized_name": p.normalized_name,
                "matched_term": p.matched_term,
            }
            for p in people_resolution.matched_people
        ],
    }

    search_query_plan = query_plan
    if people_resolution.has_people and people_resolution.residual_query.strip():
        search_query_plan = query_plan_resolver(
            people_resolution.residual_query,
            project_id=project_id,
            settings=effective_settings,
            understander=understander,
        )
        people_query_plan["semantic_query"] = people_resolution.residual_query
        people_query_plan["semantic_query_plan"] = {
            "intent": search_query_plan.intent,
            "normalized_query": search_query_plan.normalized_query,
            "semantic_query_text": search_query_plan.semantic_query_text,
            "exact_terms": search_query_plan.exact_terms,
            "expanded_terms": search_query_plan.expanded_terms,
            "broad_terms": search_query_plan.broad_terms,
            "support_terms": search_query_plan.support_terms,
        }

    if mode == "auto":
        if search_query_plan.intent == "ocr_text_search":
            effective_mode: SearchMode = "keyword"
        else:
            effective_mode = effective_settings.default_mode
    else:
        effective_mode = mode  # type: ignore[assignment]

    metadata_filters = dict(search_query_plan.metadata_filters or {})
    people_context_active = (
        bool(people_resolution.is_people_only)
        or str(people_resolution.people_filter_mode or "none") != "none"
    )
    force_temporal_metadata_filters = any(
        metadata_filters.get(key) not in (None, "", [], {})
        for key in _TEMPORAL_METADATA_KEYS
    ) and (not people_context_active)

    if people_context_active:
        metadata_filters = {}
    elif (not effective_settings.enable_structured_filters) and (not force_temporal_metadata_filters):
        metadata_filters = {}

    metadata_only_requested = bool(metadata_filters.get("metadata_only")) and not face_filter_active
    metadata_only_allowed = search_query_plan.intent not in _METADATA_ONLY_BLOCKED_INTENTS
    metadata_filter_skipped_reason = "not_skipped"
    if people_context_active:
        metadata_filter_skipped_reason = "people_only_query"
    elif not effective_settings.enable_structured_filters and not force_temporal_metadata_filters:
        metadata_filter_skipped_reason = "structured_filters_disabled"
    elif not effective_settings.enable_structured_filters and force_temporal_metadata_filters:
        metadata_filter_skipped_reason = "forced_temporal_metadata"
    elif search_query_plan.intent in _METADATA_ONLY_BLOCKED_INTENTS:
        metadata_filter_skipped_reason = "strong_semantic_intent"
    elif not metadata_filters:
        metadata_filter_skipped_reason = "no_metadata_filters"

    if metadata_only_requested and not metadata_only_allowed:
        metadata_filters = dict(metadata_filters)
        metadata_filters["metadata_only"] = False

    metadata_filter_active = bool(
        metadata_filters.get("year")
        or metadata_filters.get("month")
        or metadata_filters.get("months")
        or metadata_filters.get("date_from")
        or (metadata_filters.get("has_gps") is not None)
        or metadata_filters.get("camera_make")
        or metadata_filters.get("camera_model")
        or (metadata_filters.get("iso_min") is not None)
        or (metadata_filters.get("iso_max") is not None)
        or metadata_filters.get("place_terms")
    )

    return SearchPlan(
        effective_settings=effective_settings,
        query_plan=query_plan,
        search_query_plan=search_query_plan,
        people_resolution=people_resolution,
        people_query_plan=people_query_plan,
        effective_mode=effective_mode,
        metadata_filters=metadata_filters,
        metadata_filter_active=metadata_filter_active,
        metadata_only_requested=metadata_only_requested,
        metadata_only_allowed=metadata_only_allowed,
        metadata_filter_skipped_reason=metadata_filter_skipped_reason,
    )
