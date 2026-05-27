from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.search import SearchResponse
from ..services.search.tag_filter import ALLOWED_TAG_FIELDS, tag_filter_photos
from ..services.search.app_service import search_photos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects-search"])


@router.get("/{project_id}/search", response_model=SearchResponse)
def project_search(
    project_id: int,
    q: str = "",
    page: int = 1,
    page_size: int = 50,
    mode: str = Query("auto", pattern="^(auto|keyword|vector|hybrid)$"),
    debug: bool = False,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    filter: Optional[str] = Query(None, pattern="^(tag)$"),
    tag_field: Optional[str] = None,
    tag_value: Optional[str] = None,
    face_count_min: Optional[int] = Query(default=None, ge=0),
    face_count_max: Optional[int] = Query(default=None, ge=0),
    has_review_pending: Optional[bool] = None,
    has_unnamed_people: Optional[bool] = None,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Search photos within a specific project.

    When ``filter=tag`` is provided along with ``tag_field`` and ``tag_value``,
    exact tag-array filtering is used instead of keyword/vector search.
    This guarantees the result set matches the counts shown on the tags page.
    """
    if filter == "tag":
        if not tag_field or not tag_value:
            raise HTTPException(
                status_code=422,
                detail="filter=tag requires both tag_field and tag_value",
            )
        if tag_field not in ALLOWED_TAG_FIELDS:
            raise HTTPException(
                status_code=422,
                detail=f"tag_field must be one of: {sorted(ALLOWED_TAG_FIELDS)}",
            )
        total, items, debug_payload = tag_filter_photos(
            db,
            project_id=project_id,
            tag_field=tag_field,
            tag_value=tag_value,
            folder_id=folder_id,
            folder_scope=folder_scope,
            page=page,
            page_size=page_size,
        )
        return SearchResponse(
            query=tag_value,
            total=total,
            page=page,
            page_size=page_size,
            items=items,
            debug=None,
        )

    # Normal keyword / vector / hybrid search
    total, items, debug_payload = search_photos(
        db,
        q,
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
    return SearchResponse(
        query=q,
        total=total,
        page=page,
        page_size=page_size,
        items=items,
        debug=debug_payload,
    )
