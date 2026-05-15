from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: str
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    taken_at: Optional[datetime] = None
    file_size: Optional[int] = None
    status: str
    thumbnail_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PhotoDetailResponse(PhotoResponse):
    exif: Optional[Dict[str, str]] = None


class PhotoListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PhotoResponse]
