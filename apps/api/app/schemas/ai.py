from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ── AI Analysis ────────────────────────────────────────────────────────────

class AIAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    caption: Optional[str] = None
    ocr_text: Optional[str] = None
    scene_tags: Optional[List[str]] = None
    object_tags: Optional[List[str]] = None
    activity_tags: Optional[List[str]] = None
    quality_tags: Optional[List[str]] = None
    location_clues: Optional[List[str]] = None
    search_keywords: Optional[List[str]] = None
    people_count: Optional[int] = None
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime


# ── AI Jobs ────────────────────────────────────────────────────────────────

class AIJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    job_type: Optional[str] = None
    status: str
    retry_count: int
    error_message: Optional[str] = None
    prompt_template_id: Optional[int] = None
    prompt_version: Optional[int] = None
    model_name: Optional[str] = None
    model_params: Optional[Dict] = None
    raw_model_output: Optional[str] = None
    parse_error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    # joined from photos table (populated manually in router)
    file_name: Optional[str] = None


class AIJobListResponse(BaseModel):
    total: int
    items: List[AIJobResponse]


class AIStatusResponse(BaseModel):
    queued: int
    running: int
    success: int
    failed: int
    total: int
    analyzed_count: int = 0
    embedding_ready_count: int = 0
    embedding_missing_count: int = 0
    embedding_failed_count: int = 0
    embedding_stale_count: int = 0


class StartAnalysisResponse(BaseModel):
    created_jobs: int
    message: str


class RetryFailedResponse(BaseModel):
    retried_jobs: int
    message: str
