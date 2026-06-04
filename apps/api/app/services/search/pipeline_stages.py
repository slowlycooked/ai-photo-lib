"""Thin adapters for middle search pipeline stages."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .execution_context import SearchExecutionContext
from .pipeline_types import SearchPipelineDeps
from .trace_writer import SearchDebugTraceWriter
from .types import SearchCandidate

_PEOPLE_RRF_WEIGHT = 1.20


class MetadataFilterStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        *,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ):
        return self._deps.run_metadata_stage(
            db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )


class PeopleFilterStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        *,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ):
        return self._deps.run_people_stage(
            db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )


class KeywordRecallStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        *,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ):
        return self._deps.run_keyword_auxiliary_stage(
            db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )


class VectorRecallStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        *,
        execution_context: SearchExecutionContext,
        trace_writer: SearchDebugTraceWriter,
    ):
        return self._deps.run_vector_stage(
            db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )


class FusionStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        keyword_candidates: list[SearchCandidate],
        vector_scores: dict,
        *,
        execution_context: SearchExecutionContext,
    ):
        return self._deps.fuse_hybrid_candidates(
            keyword_candidates,
            vector_scores,
            execution_context.effective_settings,
            concept_candidates_count=execution_context.concept_candidates_count,
            people_results=execution_context.people_results,
            people_weight=_PEOPLE_RRF_WEIGHT,
        )


class EvidenceFilterStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def run(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        *,
        execution_context: SearchExecutionContext,
    ):
        return self._deps.apply_post_fusion_pipeline(
            db,
            candidates,
            query_plan=execution_context.search_query_plan,
            settings=execution_context.effective_settings,
            project_id=execution_context.project_id,
        )
