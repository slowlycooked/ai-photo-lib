from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.search import SearchResponse
from ..services.search_service import search_photos

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    total, items = search_photos(db, q, page=page, page_size=page_size)
    return SearchResponse(
        query=q,
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )
