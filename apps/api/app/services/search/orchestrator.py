"""Stable orchestration boundary for project-scoped search."""
from __future__ import annotations

from typing import Any
from typing import Optional

from sqlalchemy.orm import Session

from .pipeline_runner import SearchPipelineRunner
from .pipeline_types import SearchPipelineDeps, SearchPipelineRequest
from .result_cache import (
    SearchResultCacheEntry,
    get_project_search_cache_epoch,
    search_result_cache_get,
    search_result_cache_put,
)
from .settings_resolver import SearchSettingsResolver
from .types import SearchMode


SearchOrchestratorDeps = SearchPipelineDeps


class SearchOrchestrator:
    """Compatibility facade over the typed search pipeline runner."""

    def __init__(self, db: Session, deps: SearchPipelineDeps) -> None:
        self._db = db
        self._runner = SearchPipelineRunner(db, deps)

    @staticmethod
    def _cache_key(
        *,
        project_id: int,
        epoch: int,
        query: str,
        page: int,
        page_size: int,
        mode: str,
        debug: bool,
        folder_id: Optional[int],
        folder_scope: str,
        face_count_min: Optional[int],
        face_count_max: Optional[int],
        has_review_pending: Optional[bool],
        has_unnamed_people: Optional[bool],
    ) -> tuple[Any, ...]:
        return (
            int(project_id),
            int(epoch),
            query.strip().lower(),
            int(page),
            int(page_size),
            str(mode),
            bool(debug),
            int(folder_id or 0),
            str(folder_scope or "subtree"),
            face_count_min,
            face_count_max,
            has_review_pending,
            has_unnamed_people,
        )

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
        ttl_seconds = 0
        cache_key: Optional[tuple[Any, ...]] = None
        if project_id is not None:
            settings = SearchSettingsResolver.resolve(self._db, project_id)
            ttl_seconds = max(0, int(settings.search_result_cache_ttl_seconds))
            if ttl_seconds > 0:
                epoch = get_project_search_cache_epoch(self._db, project_id)
                cache_key = self._cache_key(
                    project_id=project_id,
                    epoch=epoch,
                    query=query,
                    page=page,
                    page_size=page_size,
                    mode=mode,
                    debug=debug,
                    folder_id=folder_id,
                    folder_scope=folder_scope,
                    face_count_min=face_count_min,
                    face_count_max=face_count_max,
                    has_review_pending=has_review_pending,
                    has_unnamed_people=has_unnamed_people,
                )
                cached = search_result_cache_get(cache_key, ttl_seconds)
                if cached is not None:
                    cached_debug = dict(cached.debug_payload or {}) if debug else None
                    if debug:
                        cached_debug["cache_hit"] = True
                        cached_debug["cache_ttl_seconds"] = ttl_seconds
                    return cached.total, cached.items, cached_debug

        result = self._runner.run(
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

        total, items, debug_payload = result
        if debug:
            debug_payload = dict(debug_payload or {})
            debug_payload["cache_hit"] = False
            debug_payload["cache_ttl_seconds"] = ttl_seconds

        if cache_key is not None and ttl_seconds > 0:
            search_result_cache_put(
                cache_key,
                SearchResultCacheEntry(
                    total=total,
                    items=items,
                    debug_payload=debug_payload,
                ),
                ttl_seconds,
            )

        return total, items, debug_payload
