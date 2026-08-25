"""Pipeline runner for project-scoped search."""
from __future__ import annotations

import logging
from time import perf_counter

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .build_plan_stage import BuildPlanStage
from .debug import build_timing_summary
from .fallback_stage import FallbackStage
from .hydration_stage import HydrationStage
from .pipeline_stages import (
    EvidenceFilterStage,
    FusionStage,
    KeywordRecallStage,
    MetadataFilterStage,
    PeopleFilterStage,
    VectorRecallStage,
)
from .pipeline_types import SearchPipelineDeps, SearchPipelineRequest, SearchPipelineResult

logger = logging.getLogger(__name__)


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


class SearchPipelineRunner:
    """Coordinates search stages while delegating policy logic to specialized modules."""

    def __init__(self, db: Session, deps: SearchPipelineDeps) -> None:
        self._db = db
        self._fallback_stage = FallbackStage(deps, deps.fallback_policy_cls(db))
        self._build_plan_stage = BuildPlanStage(deps)
        self._metadata_stage = MetadataFilterStage(deps)
        self._people_stage = PeopleFilterStage(deps)
        self._keyword_stage = KeywordRecallStage(deps)
        self._vector_stage = VectorRecallStage(deps)
        self._fusion_stage = FusionStage(deps)
        self._evidence_stage = EvidenceFilterStage(deps)
        self._hydration_stage = HydrationStage(deps)

    def run(self, request: SearchPipelineRequest) -> SearchPipelineResult:
        query = request.query.strip()
        page = request.page
        page_size = request.page_size
        project_id = request.project_id
        folder_id = request.folder_id
        folder_scope = request.folder_scope
        mode = request.mode
        debug = request.debug
        if not query:
            return SearchPipelineResult(0, [], None)
        pipeline_started_at = perf_counter()

        logger.debug(
            "[search] ── START ── project_id=%s query=%r mode=%s page=%d page_size=%d folder_id=%s folder_scope=%s",
            project_id, query, mode, page, page_size, folder_id, folder_scope,
        )

        build_plan_started_at = perf_counter()
        build_plan_result = self._build_plan_stage.run(
            self._db,
            request=request,
            query=query,
            logger=logger,
        )
        execution_context = build_plan_result.execution_context
        trace = build_plan_result.trace
        trace_writer = build_plan_result.trace_writer
        debug_builder = build_plan_result.debug_builder
        folder_photo_subquery = build_plan_result.folder_photo_subquery
        trace_writer.write_stage(
            "build_plan",
            duration_ms=_elapsed_ms(build_plan_started_at),
        )

        def _build_debug_payload(**kwargs) -> dict:
            return debug_builder.build(**kwargs)

        def _finish_result(
            result: SearchPipelineResult,
            hydration_started_at: float,
        ) -> SearchPipelineResult:
            result_event = next(
                (event for event in reversed(trace) if event.get("stage") == "result"),
                None,
            )
            if result_event is not None:
                result_event["duration_ms"] = _elapsed_ms(hydration_started_at)
                result_event["total_ms"] = _elapsed_ms(pipeline_started_at)
            if result.debug_payload is not None:
                result.debug_payload["timings_ms"] = build_timing_summary(
                    trace,
                    execution_context.search_query_plan.planner_debug,
                )
            return result

        metadata_stage = self._metadata_stage.run(
            self._db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        execution_context.constrained_photo_ids = metadata_stage.constrained_photo_ids
        if metadata_stage.metadata_only_candidates is not None:
            logger.debug("[search] path=metadata-only filters=%s", execution_context.metadata_filters)
            hydration_started_at = perf_counter()
            result = self._hydration_stage.metadata_only_result(
                self._db,
                metadata_stage.metadata_only_candidates,
                execution_context=execution_context,
                project_id=project_id or 0,
                page=page,
                page_size=page_size,
                debug=debug,
                trace=trace,
                debug_factory=_build_debug_payload,
            )
            logger.debug(
                "[search] ── DONE ── path=metadata-only total=%d items=%d page=%d",
                result.total,
                len(result.items),
                page,
            )
            return _finish_result(result, hydration_started_at)

        people_stage = self._people_stage.run(
            self._db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        execution_context.constrained_photo_ids = people_stage.constrained_photo_ids
        execution_context.people_results = people_stage.people_results
        execution_context.matched_person_ids = people_stage.matched_person_ids
        execution_context.people_candidates_debug = people_stage.people_candidates_debug
        if people_stage.people_only_candidates is not None:
            hydration_started_at = perf_counter()
            result = self._hydration_stage.people_only_result(
                self._db,
                people_stage.people_only_candidates,
                execution_context=execution_context,
                project_id=project_id or 0,
                page=page,
                page_size=page_size,
                debug=debug,
                trace=trace,
                debug_factory=_build_debug_payload,
            )
            logger.debug(
                "[search] ── DONE ── path=people-only total=%d items=%d page=%d",
                result.total,
                len(result.items),
                page,
            )
            return _finish_result(result, hydration_started_at)

        try:
            keyword_stage = self._keyword_stage.run(
                self._db,
                execution_context=execution_context,
                trace_writer=trace_writer,
            )
            keyword_results = keyword_stage.keyword_results
            merged_keyword_results = keyword_stage.merged_keyword_results
            execution_context.concept_candidates_count = keyword_stage.concept_candidates_count
            execution_context.people_visual_candidates_count = keyword_stage.people_visual_candidates_count
            execution_context.concept_debug_info = keyword_stage.concept_debug_info
        except SQLAlchemyError as exc:
            hydration_started_at = perf_counter()
            fallback_result = self._fallback_stage.handle_keyword_error(
                error=exc,
                execution_context=execution_context,
                query=query,
                project_id=project_id,
                folder_photo_subquery=folder_photo_subquery,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_builder=debug_builder,
            )
            if fallback_result is not None:
                return _finish_result(fallback_result, hydration_started_at)
            raise

        if execution_context.effective_mode == "keyword" or project_id is None:
            logger.debug("[search] path=keyword-only")
            hydration_started_at = perf_counter()
            result = self._hydration_stage.keyword_only_result(
                self._db,
                merged_keyword_results,
                execution_context=execution_context,
                project_id=project_id or 0,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_factory=_build_debug_payload,
                keyword_candidates_count=len(keyword_results),
            )
            logger.debug(
                "[search] ── DONE ── path=keyword-only total=%d items=%d page=%d",
                result.total, len(result.items), page,
            )
            return _finish_result(result, hydration_started_at)

        vector_stage = self._vector_stage.run(
            self._db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        vector_scores = vector_stage.vector_scores
        embedding_model = vector_stage.embedding_model
        fallback_reason = vector_stage.fallback_reason
        stale_embedding_filtered = vector_stage.stale_embedding_filtered
        if vector_stage.error is not None:
            hydration_started_at = perf_counter()
            result = self._fallback_stage.handle_vector_error(
                error=vector_stage.error,
                execution_context=execution_context,
                keyword_results=keyword_results,
                merged_keyword_results=merged_keyword_results,
                embedding_model=embedding_model,
                fallback_reason=fallback_reason,
                project_id=project_id,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_builder=debug_builder,
                logger=logger,
                query=query,
            )
            return _finish_result(result, hydration_started_at)

        if execution_context.effective_mode == "vector":
            logger.debug("[search] path=vector-only")
            hydration_started_at = perf_counter()
            result = self._hydration_stage.vector_only_result(
                self._db,
                vector_scores,
                execution_context=execution_context,
                project_id=project_id or 0,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_factory=_build_debug_payload,
                embedding_model=embedding_model,
                keyword_candidates_count=len(keyword_results),
            )
            return _finish_result(result, hydration_started_at)

        logger.debug(
            "[search] path=hybrid rrf_merge kw_candidates=%d vec_candidates=%d people_candidates=%d",
            len(merged_keyword_results), len(vector_scores), len(execution_context.people_results),
        )
        fusion_started_at = perf_counter()
        fusion_result = self._fusion_stage.run(
            merged_keyword_results,
            vector_scores,
            execution_context=execution_context,
        )
        merged = fusion_result.candidates
        fusion_result.trace_event["duration_ms"] = _elapsed_ms(fusion_started_at)
        logger.debug(
            "[search] rrf_merge done merged=%d top_final_scores=%s",
            len(merged),
            [round(candidate.final_score, 6) for candidate in merged[:5]],
        )
        trace_writer.write(fusion_result.trace_event)

        evidence_started_at = perf_counter()
        post_fusion = self._evidence_stage.run(
            self._db,
            merged,
            execution_context=execution_context,
        )
        merged = post_fusion.candidates
        if post_fusion.trace_events:
            post_fusion.trace_events[0]["duration_ms"] = _elapsed_ms(evidence_started_at)
        trace_writer.extend(post_fusion.trace_events)

        hydration_started_at = perf_counter()
        result = self._hydration_stage.hybrid_result(
            self._db,
            merged,
            execution_context=execution_context,
            project_id=project_id or 0,
            page=page,
            page_size=page_size,
            debug=debug,
            trace_writer=trace_writer,
            debug_factory=_build_debug_payload,
            embedding_model=embedding_model,
            keyword_candidates_count=len(keyword_results),
            vector_candidates_count=len(vector_scores),
            filtered_count=post_fusion.filtered_count,
            filtered_out=post_fusion.filtered_out,
            vector_only_rejected_count=post_fusion.vector_only_rejected_count,
            vector_only_reject_reasons=post_fusion.vector_only_reject_reasons,
            stale_embedding_filtered=stale_embedding_filtered,
        )
        logger.debug(
            "[search] ── DONE ── path=hybrid total=%d items=%d page=%d",
            result.total, len(result.items), page,
        )
        return _finish_result(result, hydration_started_at)
