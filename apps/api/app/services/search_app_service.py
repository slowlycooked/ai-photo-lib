"""SearchAppService — project-scoped search application service.

Wraps the new ``app.services.search.app_service.search_photos`` function
behind an object-oriented interface that was previously used by routers.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from .search.app_service import search_photos
from .search.types import SearchMode

logger = logging.getLogger(__name__)


class SearchAppService:
    """Application service for project-scoped photo search.

    Usage::

        service = SearchAppService(db, project_id)
        total, items, debug_payload = service.search(
            query="夜晚古建筑",
            mode="hybrid",
            page=1,
            page_size=50,
        )
    """

    def __init__(self, db: Session, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    def search(
        self,
        query: str,
        *,
        mode: SearchMode = "hybrid",
        page: int = 1,
        page_size: int = 50,
        folder_id: Optional[int] = None,
        folder_scope: str = "subtree",
        debug: bool = False,
    ) -> tuple[int, list, Optional[dict]]:
        """Search photos. Returns (total, items, debug_payload)."""
        return search_photos(
            self._db,
            query,
            page=page,
            page_size=page_size,
            project_id=self._project_id,
            folder_id=folder_id,
            folder_scope=folder_scope,
            mode=mode,
            debug=debug,
        )
