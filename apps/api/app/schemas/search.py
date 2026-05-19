from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    page_size: int
    items: List[SearchResultItem]
