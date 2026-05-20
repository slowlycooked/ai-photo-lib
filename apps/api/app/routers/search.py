from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.search import SearchResponse
from ..services.search_service import search_photos

logger = logging.getLogger(__name__)

# DEPRECATED: Use /projects/{project_id}/search instead.
router = APIRouter(prefix="/search", tags=["search [deprecated]"])

_DEPRECATION_MSG = (
    "Global /search endpoint is deprecated. "
    "Use /projects/{project_id}/search instead."
)


@router.get("", response_model=SearchResponse, deprecated=True)
def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    """[DEPRECATED] Use GET /projects/{project_id}/search instead."""
    logger.warning(_DEPRECATION_MSG)
    total, items = search_photos(
        db, q, page=page, page_size=page_size, project_id=project_id,
        folder_id=folder_id, folder_scope=folder_scope
    )
    return SearchResponse(
        query=q,
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )
