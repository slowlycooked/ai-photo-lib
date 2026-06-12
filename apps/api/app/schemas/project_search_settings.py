"""Pydantic schemas for project search settings."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectSearchSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    default_mode: str
    keyword_top_k: int
    vector_top_k: int
    page_size_default: int
    page_size_max: int
    rrf_k: int
    keyword_weight: float
    vector_weight: float
    vector_min_score: float
    keyword_field_weights: Optional[Dict[str, float]] = None
    vector_field_weights: Optional[Dict[str, float]] = None
    ocr_query_vector_field_weights: Optional[Dict[str, float]] = None
    enable_query_understanding: bool
    enable_structured_filters: bool
    enable_semantic_tag_boost: bool
    search_result_cache_ttl_seconds: int
    search_quality_settings: Optional[Dict] = None
    created_at: datetime
    updated_at: datetime


class ProjectSearchSettingsUpdate(BaseModel):
    default_mode: Optional[str] = Field(None, pattern="^(auto|keyword|vector|hybrid)$")
    keyword_top_k: Optional[int] = Field(None, ge=1, le=10000)
    vector_top_k: Optional[int] = Field(None, ge=1, le=2000)
    page_size_default: Optional[int] = Field(None, ge=1, le=500)
    page_size_max: Optional[int] = Field(None, ge=1, le=1000)
    rrf_k: Optional[int] = Field(None, ge=1, le=10000)
    keyword_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    vector_weight: Optional[float] = Field(None, ge=0.0, le=1.0)
    vector_min_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    keyword_field_weights: Optional[Dict[str, float]] = None
    vector_field_weights: Optional[Dict[str, float]] = None
    ocr_query_vector_field_weights: Optional[Dict[str, float]] = None
    enable_query_understanding: Optional[bool] = None
    enable_structured_filters: Optional[bool] = None
    enable_semantic_tag_boost: Optional[bool] = None
    search_result_cache_ttl_seconds: Optional[int] = Field(None, ge=0, le=86400)
    search_quality_settings: Optional[Dict] = None
