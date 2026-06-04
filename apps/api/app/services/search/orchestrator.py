"""Stable orchestration boundary for project-scoped search."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from .pipeline_runner import SearchPipelineRunner
from .pipeline_types import SearchPipelineDeps, SearchPipelineRequest
from .types import SearchMode


SearchOrchestratorDeps = SearchPipelineDeps


class SearchOrchestrator:
    """Compatibility facade over the typed search pipeline runner."""

    def __init__(self, db: Session, deps: SearchPipelineDeps) -> None:
        self._runner = SearchPipelineRunner(db, deps)

    def search(
        self,
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
        return self._runner.run(
            SearchPipelineRequest(
                query=query,
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
        ).as_tuple()
