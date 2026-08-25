"""Recall orchestration helpers for search."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ..query_understanding_service import SearchQueryPlan
from .concept_recall import ConceptRecallService
from .people_visual_recall import PeopleVisualRecallService
from .types import EffectiveSearchSettings, SearchCandidate


@dataclass(frozen=True)
class AuxiliaryRecallResult:
    concept_results: list[SearchCandidate]
    people_visual_results: list[SearchCandidate]
    concept_debug: dict
    trace_events: list[dict]

    @property
    def concept_candidates_count(self) -> int:
        return len(self.concept_results)

    @property
    def people_visual_candidates_count(self) -> int:
        return len(self.people_visual_results)


def recall_auxiliary_candidates(
    db: Session,
    query_plan: SearchQueryPlan,
    *,
    project_id: Optional[int],
    settings: EffectiveSearchSettings,
    folder_photo_subquery: Optional[Select],
    constrained_photo_ids: Optional[set[int]],
    concept_terms: list[str],
    concept_facets: list[str],
    concept_entity_terms: list[str],
    concept_recall_service_cls=ConceptRecallService,
    people_visual_recall_service_cls=PeopleVisualRecallService,
) -> AuxiliaryRecallResult:
    """Recall auxiliary candidates that complement keyword recall."""
    concept_results: list[SearchCandidate] = []
    people_visual_results: list[SearchCandidate] = []

    uses_v2_contract = (
        str(getattr(query_plan, "planner_contract_version", "1")) == "2"
    )
    concept_recall_enabled = (
        not uses_v2_contract or settings.legacy_concept_recall_enabled
    )

    if project_id is not None and concept_recall_enabled:
        concept_results = concept_recall_service_cls(db, settings).search(
            query_plan,
            project_id=project_id,
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
        )
    if project_id is not None:
        people_visual_results = people_visual_recall_service_cls(db, settings).search(
            query_plan,
            project_id=project_id,
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
        )

    concept_debug = {
        "enabled": concept_recall_enabled,
        "reason": (
            "connected" if concept_recall_enabled else "disabled_for_query_plan_v2"
        ),
        "concept_terms": concept_terms,
        "concept_facets": concept_facets,
        "entity_terms": concept_entity_terms,
        "candidates": len(concept_results),
        "top_scores": [round(candidate.keyword_score, 6) for candidate in concept_results[:5]],
    }
    trace_events = [
        {
            "stage": "concept_recall",
            "enabled": concept_recall_enabled,
            "reason": (
                "connected" if concept_recall_enabled else "disabled_for_query_plan_v2"
            ),
            "concept_terms": concept_terms,
            "concept_facets": concept_facets,
            "candidates": len(concept_results),
            "top_scores": [round(candidate.keyword_score, 4) for candidate in concept_results[:5]],
        },
        {
            "stage": "people_visual_recall",
            "candidates": len(people_visual_results),
            "top_scores": [round(candidate.keyword_score, 4) for candidate in people_visual_results[:5]],
        },
    ]

    return AuxiliaryRecallResult(
        concept_results=concept_results,
        people_visual_results=people_visual_results,
        concept_debug=concept_debug,
        trace_events=trace_events,
    )
