from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    file_name: str
    mime_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    taken_at: Optional[datetime] = None
    file_size: Optional[int] = None
    status: str
    thumbnail_path: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    country_name: Optional[str] = None
    admin1: Optional[str] = None
    admin2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    formatted_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PhotoDetailResponse(PhotoResponse):
    exif: Optional[Dict[str, str]] = None
    # Structured metadata
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_altitude: Optional[float] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    admin1: Optional[str] = None
    admin2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    formatted_address: Optional[str] = None
    location_source: Optional[str] = None
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


class PhotoDeleteResponse(BaseModel):
    project_id: int
    photo_id: int
    deleted_thumbnail: bool
    deleted_original: bool
    queued_original_for_trash: bool = False
    message: str


class PhotoBatchDeleteRequest(BaseModel):
    photo_ids: List[int] = Field(default_factory=list, min_length=1)
    delete_original: bool = True


class PhotoBatchDeleteResponse(BaseModel):
    project_id: int
    requested_count: int
    deleted_count: int
    deleted_photo_ids: List[int]
    not_found_photo_ids: List[int]
    deleted_thumbnail_count: int
    deleted_original_count: int
    queued_original_for_trash_count: int = 0
    message: str
