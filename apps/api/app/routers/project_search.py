from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.search import SearchResponse
from ..services.search_service import search_photos

router = APIRouter(prefix="/projects", tags=["projects-search"])


@router.get("/{project_id}/search", response_model=SearchResponse)
def project_search(
    project_id: int,
    q: str,
    page: int = 1,
    page_size: int = 50,
    mode: str = Query("hybrid", pattern="^(keyword|vector|hybrid)$"),
    debug: bool = False,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Search photos within a specific project."""
    total, items = search_photos(
        db,
        q,
        page=page,
        page_size=page_size,
        project_id=project_id,
        folder_id=folder_id,
        folder_scope=folder_scope,
        mode=mode,
        debug=debug,
    )
    return SearchResponse(query=q, total=total, page=page, page_size=page_size, items=items)
