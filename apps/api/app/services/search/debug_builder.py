"""Debug payload builder for search orchestration."""
from __future__ import annotations

import logging

from ...config import settings as global_settings
from .debug import SearchDebugContext, build_logged_debug_payload
from .execution_context import SearchExecutionContext


class SearchDebugBuilder:
    """Builds search debug payloads from execution context."""

    def __init__(
        self,
        logger: logging.Logger,
        execution_context: SearchExecutionContext,
        trace: list[dict],
    ) -> None:
        self._logger = logger
        self._execution_context = execution_context
        self._trace = trace

    def build(self, **kwargs) -> dict:
        context = self._execution_context
        return build_logged_debug_payload(
            self._logger,
            SearchDebugContext(
                query_plan=context.search_query_plan,
                settings=context.effective_settings,
                trace=self._trace,
                embedding_dimension=global_settings.embedding_dimension,
                people_query_plan=context.people_query_plan,
                people_candidates=context.people_candidates_debug,
                people_filter_mode=context.people_resolution.people_filter_mode,
                matched_person_ids=context.matched_person_ids,
                metadata_filter_active=context.metadata_filter_active,
                metadata_filter_skipped_reason=context.metadata_filter_skipped_reason,
                metadata_only_allowed=context.metadata_only_allowed,
                concept_terms=context.concept_terms_for_debug,
                concept_entity_terms=context.concept_entity_terms_for_debug,
                concept_debug=context.concept_debug_info,
                concept_candidates=context.concept_candidates_count,
                people_visual_candidates=context.people_visual_candidates_count,
            ),
            **kwargs,
        )
