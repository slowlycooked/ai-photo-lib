from __future__ import annotations

"""Search Application Service (Phase 3 / P0).

Wraps the existing ``search_service.py`` as a proper Application Service:
* Validates project context
* Resolves effective settings via ``ProjectSettingsResolver``
* Delegates to the existing search implementation

Future iterations will inline the search logic here and remove the
``search_service`` module dependency.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..services.project_settings import ProjectSettingsResolver
from ..services.search_service import SearchMode, search_photos
from ..schemas.search import SearchResponse

logger = logging.getLogger(__name__)


class SearchAppService:
    """Application service for project-scoped photo search.

    Usage::

        service = SearchAppService(db, project_id)
        total, items = service.search(
            query="夜晚古建筑",
            mode="hybrid",
            page=1,
            page_size=50,
        )
    """

    def __init__(self, db: Session, project_id: int) -> None:
        self._db = db
        self._project_id = project_id
        self._effective = ProjectSettingsResolver.resolve(db, project_id)

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
    ) -> tuple[int, list]:
        """Execute a project-scoped search and return (total, items)."""
        logger.debug(
            "SearchAppService.search project_id=%s mode=%s query=%s",
            self._project_id,
            mode,
            query,
        )
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
