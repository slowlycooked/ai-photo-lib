from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    photo_id: int
    file_name: str
    thumbnail_url: str
    updated_at: datetime
    taken_at: Optional[datetime] = None
    width: Optional[int] = None
    height: Optional[int] = None
    caption: Optional[str] = None
    matched_tags: List[str]
    score: float
    keyword_score: Optional[float] = None
    vector_score: Optional[float] = None
    rrf_score: Optional[float] = None
    match_source: Optional[List[str]] = None
    field_scores: Optional[Dict[str, float]] = None
    explain: Optional[Dict[str, Any]] = None  # per-result keyword/vector explain


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    page_size: int
    items: List[SearchResultItem]
    debug: Optional[Dict[str, Any]] = None
