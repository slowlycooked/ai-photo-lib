"""Fallback/error handling stage for the search pipeline."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from .execution_context import SearchExecutionContext
from .fallback_policy import SearchFallbackPolicy
from .pipeline_types import SearchPipelineDeps, SearchPipelineResult
from .trace_writer import SearchDebugTraceWriter


class FallbackStage:
    def __init__(self, deps: SearchPipelineDeps, fallback_policy: SearchFallbackPolicy) -> None:
        self._deps = deps
        self._fallback_policy = fallback_policy

    def handle_keyword_error(
        self,
        *,
        error: SQLAlchemyError,
        execution_context: SearchExecutionContext,
        query: str,
        project_id: Optional[int],
        folder_photo_subquery,
        page: int,
        page_size: int,
        debug: bool,
        trace_writer: SearchDebugTraceWriter,
        debug_builder,
    ) -> Optional[SearchPipelineResult]:
        fallback_result = self._fallback_policy.handle_keyword_stage_error(
            error=error,
            execution_context=execution_context,
            query=query,
            project_id=project_id,
            folder_photo_subquery=folder_photo_subquery,
            page=page,
            page_size=page_size,
            debug=debug,
            trace_writer=trace_writer,
            debug_builder=debug_builder,
            build_result_items_fn=self._deps.build_result_items,
        )
        if fallback_result is None:
            return None
        return SearchPipelineResult(*fallback_result)

    def handle_vector_error(
        self,
        *,
        error: Exception,
        execution_context: SearchExecutionContext,
        keyword_results,
        merged_keyword_results,
        embedding_model: str,
        fallback_reason: str,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace_writer: SearchDebugTraceWriter,
        debug_builder,
        logger: logging.Logger,
        query: str,
    ) -> SearchPipelineResult:
        logger.warning(
            "Vector search fallback to keyword. project_id=%s query=%r error=%s error_type=%s error_repr=%r",
            project_id,
            query,
            error,
            type(error).__name__,
            error,
        )
        return SearchPipelineResult(
            *self._fallback_policy.handle_vector_stage_error(
                error=error,
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
                attach_people_explain=self._deps.attach_people_explain,
                build_result_items_fn=self._deps.build_result_items,
            )
        )
