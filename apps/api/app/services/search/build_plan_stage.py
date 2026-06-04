"""Build-plan stage for the typed search pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .debug_builder import SearchDebugBuilder
from .execution_context import SearchExecutionContext
from .pipeline_types import SearchPipelineDeps, SearchPipelineRequest
from .query_understanding import build_query_plan_trace_event
from .trace_writer import SearchDebugTraceWriter


@dataclass(frozen=True)
class BuildPlanStageResult:
    execution_context: SearchExecutionContext
    trace: list[dict]
    trace_writer: SearchDebugTraceWriter
    debug_builder: SearchDebugBuilder
    folder_photo_subquery: object


class BuildPlanStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        *,
        request: SearchPipelineRequest,
        query: str,
        logger: logging.Logger,
    ) -> BuildPlanStageResult:
        trace: list[dict] = []
        trace_writer = SearchDebugTraceWriter(trace)
        trace_writer.write_stage(
            "input",
            query=query,
            mode=request.mode,
            page=request.page,
            page_size=request.page_size,
            folder_id=request.folder_id,
            folder_scope=request.folder_scope,
        )

        face_filter_active = (
            request.face_count_min is not None
            or request.face_count_max is not None
            or request.has_review_pending is not None
            or request.has_unnamed_people is not None
        )

        plan = self._deps.build_search_plan(
            db,
            query=query,
            mode=request.mode,
            project_id=request.project_id,
            face_filter_active=face_filter_active,
            settings_resolver_cls=self._deps.settings_resolver_cls,
            query_plan_resolver=self._deps.query_plan_resolver,
            understander=self._deps.understander,
            people_query_resolver=self._deps.people_query_resolver,
            people_resolution_cls=self._deps.people_resolution_cls,
        )
        execution_context = SearchExecutionContext.from_plan(
            plan,
            trace,
            project_id=request.project_id,
            page_size=request.page_size,
        )
        self._write_plan_trace(execution_context, trace_writer)
        self._log_plan(logger, execution_context, query, request.project_id)

        folder_photo_subquery = self._resolve_folder_filter(
            db,
            request=request,
            execution_context=execution_context,
            trace_writer=trace_writer,
            logger=logger,
        )
        self._resolve_face_filter(
            db,
            request=request,
            face_filter_active=face_filter_active,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        self._prepare_concept_debug(request.project_id, execution_context)

        return BuildPlanStageResult(
            execution_context=execution_context,
            trace=trace,
            trace_writer=trace_writer,
            debug_builder=SearchDebugBuilder(logger, execution_context, trace),
            folder_photo_subquery=folder_photo_subquery,
        )

    def _write_plan_trace(
        self,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ) -> None:
        trace_writer.write_stage(
            "settings",
            default_mode=execution_context.effective_settings.default_mode,
            keyword_top_k=execution_context.effective_settings.keyword_top_k,
            vector_top_k=execution_context.effective_settings.vector_top_k,
            rrf_k=execution_context.effective_settings.rrf_k,
            keyword_weight=execution_context.effective_settings.keyword_weight,
            vector_weight=execution_context.effective_settings.vector_weight,
            vector_min_score=execution_context.effective_settings.vector_min_score,
            enable_query_understanding=execution_context.effective_settings.enable_query_understanding,
            enable_structured_filters=execution_context.effective_settings.enable_structured_filters,
            enable_semantic_tag_boost=execution_context.effective_settings.enable_semantic_tag_boost,
        )
        trace_writer.write(build_query_plan_trace_event(execution_context.query_plan))
        trace_writer.write_stage(
            "people_query",
            has_people=execution_context.people_resolution.has_people,
            people_filter_mode=execution_context.people_resolution.people_filter_mode,
            matched_person_ids=execution_context.people_resolution.matched_person_ids,
            residual_query=execution_context.people_resolution.residual_query,
            is_people_only=execution_context.people_resolution.is_people_only,
        )
        if execution_context.people_resolution.has_people and execution_context.people_resolution.residual_query.strip():
            trace_writer.write(
                build_query_plan_trace_event(
                    execution_context.search_query_plan,
                    stage="query_plan_effective",
                    include_recommended_profile=False,
                )
            )

    def _log_plan(
        self,
        logger: logging.Logger,
        execution_context: SearchExecutionContext,
        query: str,
        project_id: Optional[int],
    ) -> None:
        logger.debug(
            "[search] effective_settings default_mode=%s kw_top_k=%d vec_top_k=%d "
            "rrf_k=%d kw_weight=%.2f vec_weight=%.2f vec_min_score=%.4f "
            "enable_qu=%s enable_filters=%s enable_tag_boost=%s",
            execution_context.effective_settings.default_mode,
            execution_context.effective_settings.keyword_top_k,
            execution_context.effective_settings.vector_top_k,
            execution_context.effective_settings.rrf_k,
            execution_context.effective_settings.keyword_weight,
            execution_context.effective_settings.vector_weight,
            execution_context.effective_settings.vector_min_score,
            execution_context.effective_settings.enable_query_understanding,
            execution_context.effective_settings.enable_structured_filters,
            execution_context.effective_settings.enable_semantic_tag_boost,
        )
        logger.debug(
            "[search] query_plan intent=%s exact=%s expanded=%s broad=%s normalized=%r",
            execution_context.query_plan.intent,
            execution_context.query_plan.exact_terms,
            execution_context.query_plan.expanded_terms,
            execution_context.query_plan.broad_terms,
            execution_context.query_plan.normalized_query,
        )
        logger.debug(
            "[search] people_query has_people=%s mode=%s matched_person_ids=%s residual=%r",
            execution_context.people_resolution.has_people,
            execution_context.people_resolution.people_filter_mode,
            execution_context.people_resolution.matched_person_ids,
            execution_context.people_resolution.residual_query,
        )
        logger.debug(
            "[search] resolved mode=%s project_id=%s query=%r intent=%s",
            execution_context.effective_mode,
            project_id,
            query,
            execution_context.search_query_plan.intent,
        )
        if execution_context.metadata_only_requested and not execution_context.metadata_only_allowed:
            logger.debug(
                "[search] metadata_only ignored due to semantic intent=%s",
                execution_context.search_query_plan.intent,
            )

    def _resolve_folder_filter(
        self,
        db: Session,
        *,
        request: SearchPipelineRequest,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
        logger: logging.Logger,
    ):
        folder_photo_subquery = (
            self._deps.resolve_folder_photo_subquery(
                db,
                project_id=request.project_id,
                folder_id=request.folder_id,
                folder_scope=request.folder_scope,
            )
            if request.project_id is not None
            else None
        )
        execution_context.folder_photo_subquery = folder_photo_subquery

        if request.folder_id is not None:
            folder_count = (
                int(
                    db.query(func.count())
                    .select_from(folder_photo_subquery.subquery())
                    .scalar()
                    or 0
                )
                if folder_photo_subquery is not None
                else None
            )
            trace_writer.write_stage(
                "folder_filter",
                folder_id=request.folder_id,
                scope=request.folder_scope,
                photo_ids_count=folder_count,
            )
            logger.debug(
                "[search] folder_filter folder_id=%s scope=%s photo_ids_count=%s",
                request.folder_id,
                request.folder_scope,
                folder_count,
            )
        return folder_photo_subquery

    def _resolve_face_filter(
        self,
        db: Session,
        *,
        request: SearchPipelineRequest,
        face_filter_active: bool,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ) -> None:
        if request.project_id is None or not face_filter_active:
            return

        face_filter_photo_ids = self._deps.resolve_face_filter_photo_ids(
            db,
            project_id=request.project_id,
            face_count_min=request.face_count_min,
            face_count_max=request.face_count_max,
            has_review_pending=request.has_review_pending,
            has_unnamed_people=request.has_unnamed_people,
        )
        execution_context.constrained_photo_ids = (
            set(face_filter_photo_ids)
            if execution_context.constrained_photo_ids is None
            else execution_context.constrained_photo_ids & face_filter_photo_ids
        )
        trace_writer.write_stage(
            "face_filter",
            face_count_min=request.face_count_min,
            face_count_max=request.face_count_max,
            has_review_pending=request.has_review_pending,
            has_unnamed_people=request.has_unnamed_people,
            matched_count=len(face_filter_photo_ids),
            constrained_count=len(execution_context.constrained_photo_ids),
        )

    def _prepare_concept_debug(
        self,
        project_id: Optional[int],
        execution_context: SearchExecutionContext,
    ) -> None:
        (
            concept_terms_for_debug,
            concept_entity_terms_for_debug,
            concept_facets_for_debug,
        ) = self._deps.derive_concept_query_context(execution_context.search_query_plan)
        execution_context.concept_terms_for_debug = concept_terms_for_debug
        execution_context.concept_entity_terms_for_debug = concept_entity_terms_for_debug
        execution_context.concept_facets_for_debug = concept_facets_for_debug
        execution_context.concept_candidates_count = 0
        execution_context.people_visual_candidates_count = 0
        execution_context.concept_debug_info = {
            "enabled": project_id is not None,
            "reason": "service_not_connected_to_rrf_yet" if project_id is None else "connected",
            "concept_terms": concept_terms_for_debug,
            "concept_facets": concept_facets_for_debug,
            "entity_terms": concept_entity_terms_for_debug,
            "candidates": execution_context.concept_candidates_count,
            "top_scores": [],
        }
