"""Fallback policy handling for search pipeline failures."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..query_understanding_service import understand_query
from .execution_context import SearchExecutionContext
from .metadata_recall import MetadataRecallService
from .result_hydrator import build_result_items


class SearchFallbackPolicy:
    """Handles metadata and keyword fallback behavior in orchestrated search."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def handle_keyword_stage_error(
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
        trace_writer,
        debug_builder,
        build_result_items_fn=build_result_items,
    ) -> Optional[tuple[int, list, Optional[dict]]]:
        fallback_metadata_filters = execution_context.metadata_filters
        if project_id is not None and not execution_context.metadata_filter_active:
            fallback_metadata_filters = understand_query(
                query,
                project_id=project_id,
                concept_taxonomy=execution_context.effective_settings.concept_taxonomy,
            ).metadata_filters

        fallback_active = bool(
            fallback_metadata_filters.get("year")
            or fallback_metadata_filters.get("month")
            or fallback_metadata_filters.get("date_from")
            or fallback_metadata_filters.get("place_terms")
        )
        if not (fallback_active and project_id is not None):
            return None

        self._db.rollback()
        meta_results = MetadataRecallService(self._db, project_id).search(
            metadata_filters=fallback_metadata_filters,
            folder_photo_subquery=folder_photo_subquery,
        )
        total, items = build_result_items_fn(
            self._db,
            meta_results,
            project_id=project_id,
            mode="hybrid",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_stage(
            "keyword_recall",
            fallback="metadata",
            error=str(error),
            metadata_candidates=len(meta_results),
        )

        debug_payload = None
        if debug:
            debug_payload = debug_builder.build(
                mode="metadata",
                keyword_candidates=0,
                vector_candidates=0,
                merged_candidates=len(meta_results),
                fallback_reason=str(error),
                metadata_filters=fallback_metadata_filters,
                metadata_candidates=len(meta_results),
                metadata_only=True,
            )
        return total, items, debug_payload

    def handle_vector_stage_error(
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
        trace_writer,
        debug_builder,
        attach_people_explain,
        build_result_items_fn=build_result_items,
    ) -> tuple[int, list, Optional[dict]]:
        if isinstance(error, SQLAlchemyError):
            try:
                self._db.rollback()
            except Exception:
                pass

        if execution_context.effective_mode == "vector":
            trace_writer.write_result(
                path="vector-error",
                total=0,
                items_in_page=0,
                page=page,
            )
            debug_payload = None
            if debug:
                debug_payload = debug_builder.build(
                    mode="vector",
                    embedding_model=embedding_model,
                    keyword_candidates=len(keyword_results),
                    vector_candidates=0,
                    merged_candidates=0,
                    fallback_reason=fallback_reason,
                )
            return 0, [], debug_payload

        total, items = build_result_items_fn(
            self._db,
            attach_people_explain(merged_keyword_results, execution_context.people_results),
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_result(
            path="hybrid-kw-fallback",
            total=total,
            items_in_page=len(items),
            page=page,
        )
        debug_payload = None
        if debug:
            debug_payload = debug_builder.build(
                mode="hybrid",
                embedding_model=embedding_model,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(merged_keyword_results),
                displayed_candidates=total,
                fallback_reason=fallback_reason,
            )
        return total, items, debug_payload
