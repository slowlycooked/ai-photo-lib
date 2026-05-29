"""Search execution context shared across pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.sql import Select

from .search_plan_builder import SearchPlan
from .types import EffectiveSearchSettings, SearchCandidate, SearchMode


@dataclass
class SearchExecutionContext:
    project_id: Optional[int]
    page_size: int
    effective_settings: EffectiveSearchSettings
    query_plan: object
    search_query_plan: object
    people_resolution: object
    people_query_plan: dict
    effective_mode: SearchMode
    metadata_filters: dict
    metadata_only_requested: bool
    metadata_only_allowed: bool
    metadata_filter_skipped_reason: str
    metadata_filter_active: bool
    trace: list[dict]
    folder_photo_subquery: Optional[Select] = None

    constrained_photo_ids: set[int] | None = None
    people_results: list[SearchCandidate] = field(default_factory=list)
    people_candidates_debug: list[dict] = field(default_factory=list)
    matched_person_ids: list[int] = field(default_factory=list)

    concept_terms_for_debug: list[str] = field(default_factory=list)
    concept_entity_terms_for_debug: list[str] = field(default_factory=list)
    concept_facets_for_debug: list[str] = field(default_factory=list)
    concept_candidates_count: int = 0
    people_visual_candidates_count: int = 0
    concept_debug_info: dict = field(default_factory=dict)

    @classmethod
    def from_plan(
        cls,
        plan: SearchPlan,
        trace: list[dict],
        *,
        project_id: Optional[int],
        page_size: int,
    ) -> "SearchExecutionContext":
        return cls(
            project_id=project_id,
            page_size=page_size,
            effective_settings=plan.effective_settings,
            query_plan=plan.query_plan,
            search_query_plan=plan.search_query_plan,
            people_resolution=plan.people_resolution,
            people_query_plan=plan.people_query_plan,
            effective_mode=plan.effective_mode,
            metadata_filters=plan.metadata_filters,
            metadata_only_requested=plan.metadata_only_requested,
            metadata_only_allowed=plan.metadata_only_allowed,
            metadata_filter_skipped_reason=plan.metadata_filter_skipped_reason,
            metadata_filter_active=plan.metadata_filter_active,
            trace=trace,
        )
