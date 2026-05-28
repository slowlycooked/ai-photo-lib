"""SearchService (new package) — the main entry point for photo search.

Orchestrates:
  1. SearchSettingsResolver → EffectiveSearchSettings
  2. understand_query (query understanding)
  3. folder filter resolution
  4. KeywordRecallService
  5. VectorRecallService
  6. RRF fusion
  7. ResultHydrator
  8. DebugPayload builder

For backward compatibility, ``search_photos()`` is also exposed as a
top-level function via ``apps/api/app/services/search_service.py``.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...models.ai import PhotoAIAnalysis
from ...services.folder_service import build_folder_photo_ids_subquery
from ...services.query_understanding_service import understand_query
from .concept_recall import ConceptRecallService, derive_concept_query_context
from .facet_evidence_policy import FacetEvidencePolicy
from .fallback_policy import SearchFallbackPolicy
from .filter_policy import (
    resolve_face_filter_photo_ids as resolve_face_filter_photo_ids_policy,
)
from .fusion import fuse_hybrid_candidates
from .keyword_recall import KeywordRecallService
from .metadata_recall import MetadataRecallService
from .orchestrator import SearchOrchestrator, SearchOrchestratorDeps
from .people_query_resolver import PeopleQueryResolution, resolve_people_query
from .people_visual_recall import PeopleVisualRecallService
from .people_recall import PeopleRecallService
from .post_fusion_pipeline import apply_post_fusion_pipeline
from .query_understanding import (
    SearchQueryPlan,
    build_query_plan_trace_event,
    resolve_search_query_plan,
)
from .recall_pipeline import (
    run_keyword_auxiliary_stage,
    run_metadata_stage,
    run_people_stage,
    run_vector_stage,
)
from .result_hydrator import (
    build_result_items,
    build_result_response,
)
from .search_plan_builder import build_search_plan
from .settings_resolver import SearchSettingsResolver
from .types import (
    EffectiveSearchSettings,
    SearchCandidate,
    SearchMode,
)
from .vector_recall import VectorRecallService

logger = logging.getLogger(__name__)

_PEOPLE_RRF_WEIGHT = 1.20
_FACET_EVIDENCE_POLICY = FacetEvidencePolicy()


def _build_orchestrator_deps() -> SearchOrchestratorDeps:
    return SearchOrchestratorDeps(
        build_search_plan=build_search_plan,
        settings_resolver_cls=SearchSettingsResolver,
        query_plan_resolver=resolve_search_query_plan,
        understander=understand_query,
        people_query_resolver=resolve_people_query,
        people_resolution_cls=PeopleQueryResolution,
        resolve_folder_photo_subquery=_resolve_folder_photo_subquery,
        resolve_face_filter_photo_ids=_resolve_face_filter_photo_ids,
        derive_concept_query_context=derive_concept_query_context,
        run_metadata_stage=run_metadata_stage,
        run_people_stage=run_people_stage,
        run_keyword_auxiliary_stage=run_keyword_auxiliary_stage,
        run_vector_stage=run_vector_stage,
        build_result_response=build_result_response,
        build_result_items=build_result_items,
        attach_people_explain=_attach_people_explain,
        fuse_hybrid_candidates=fuse_hybrid_candidates,
        apply_post_fusion_pipeline=apply_post_fusion_pipeline,
        fallback_policy_cls=SearchFallbackPolicy,
    )


def _core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional[PhotoAIAnalysis],
    query_plan: "SearchQueryPlan",
    settings: EffectiveSearchSettings,
) -> tuple[bool, str]:
    return _FACET_EVIDENCE_POLICY.core_facet_passes(candidate, ai_analysis, query_plan, settings)


def _compute_evidence_level(
    candidate: SearchCandidate,
    settings: Optional[EffectiveSearchSettings] = None,
) -> str:
    return _FACET_EVIDENCE_POLICY.compute_evidence_level(candidate, settings)


def _apply_evidence_scoring(
    candidates: list[SearchCandidate],
    settings: EffectiveSearchSettings,
) -> list[SearchCandidate]:
    return _FACET_EVIDENCE_POLICY.apply_evidence_scoring(candidates, settings)


def _apply_semantic_tag_boost(
    db: Session,
    candidates: list[SearchCandidate],
    query_plan: SearchQueryPlan,
    project_id: int,
) -> list[SearchCandidate]:
    boosted = _FACET_EVIDENCE_POLICY.apply_semantic_tag_boost(db, candidates, query_plan, project_id)
    logger.debug(
        "[semantic_tag_boost] applied to %d candidates expanded=%d broad=%d penalize=%d",
        len(boosted),
        len(query_plan.expanded_terms),
        len(query_plan.broad_terms),
        len(query_plan.penalize_tags),
    )
    return boosted


def _resolve_folder_photo_subquery(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[Select]:
    return build_folder_photo_ids_subquery(db, project_id, folder_id, folder_scope)


def _resolve_face_filter_photo_ids(
    db: Session,
    *,
    project_id: int,
    face_count_min: Optional[int],
    face_count_max: Optional[int],
    has_review_pending: Optional[bool],
    has_unnamed_people: Optional[bool],
) -> set[int]:
    return resolve_face_filter_photo_ids_policy(
        db,
        project_id=project_id,
        face_count_min=face_count_min,
        face_count_max=face_count_max,
        has_review_pending=has_review_pending,
        has_unnamed_people=has_unnamed_people,
    )


def _attach_people_explain(
    candidates: list[SearchCandidate],
    people_results: list[SearchCandidate],
) -> list[SearchCandidate]:
    """Attach people explain payload to existing candidate rows by photo_id."""
    if not candidates or not people_results:
        return candidates
    by_photo = {c.photo_id: c for c in people_results}
    for candidate in candidates:
        people_hit = by_photo.get(candidate.photo_id)
        if not people_hit:
            continue
        candidate.people_score = people_hit.people_score
        candidate.people_rank = people_hit.people_rank
        candidate.people_explain = dict(people_hit.people_explain)
        if "people" not in candidate.match_source:
            candidate.match_source.append("people")
    return candidates


def search_photos(
    db: Session,
    query: str,
    page: int = 1,
    page_size: int = 50,
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    mode: SearchMode = "hybrid",
    debug: bool = False,
    face_count_min: Optional[int] = None,
    face_count_max: Optional[int] = None,
    has_review_pending: Optional[bool] = None,
    has_unnamed_people: Optional[bool] = None,
) -> tuple[int, list, Optional[dict]]:
    orchestrator = SearchOrchestrator(db, _build_orchestrator_deps())
    return orchestrator.search(
        query,
        page=page,
        page_size=page_size,
        project_id=project_id,
        folder_id=folder_id,
        folder_scope=folder_scope,
        mode=mode,
        debug=debug,
        face_count_min=face_count_min,
        face_count_max=face_count_max,
        has_review_pending=has_review_pending,
        has_unnamed_people=has_unnamed_people,
    )
