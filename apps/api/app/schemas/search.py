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
    # Evidence / filter debug
    evidence_level: Optional[str] = None
    rank_reason: Optional[str] = None
    filter_reason: Optional[str] = None
    term_level_hits: Optional[Dict[str, Any]] = None
    negative_hits: Optional[List[str]] = None
    core_facet_passed: Optional[bool] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    # EXIF / Photo metadata fields
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[str] = None
    aperture: Optional[str] = None
    exposure_time: Optional[str] = None
    iso: Optional[int] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    country_name: Optional[str] = None
    admin1: Optional[str] = None
    admin2: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    formatted_address: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    page: int
    page_size: int
    items: List[SearchResultItem]
    debug: Optional[Dict[str, Any]] = None
