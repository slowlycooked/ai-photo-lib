from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: Optional[int] = None
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
    # Structured metadata
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_altitude: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[str] = None
    aperture: Optional[str] = None
    exposure_time: Optional[str] = None
    iso: Optional[int] = None
    orientation: Optional[int] = None


class PhotoListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[PhotoResponse]
