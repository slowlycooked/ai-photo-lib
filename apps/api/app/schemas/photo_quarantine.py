from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectPhotoQuarantineSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    enabled: bool
    dry_run: bool
    start_hour: int
    end_hour: int
    timezone: str
    model_name: str
    retention_days: int
    created_at: datetime
    updated_at: datetime


class ProjectPhotoQuarantineSettingsUpdate(BaseModel):
    enabled: bool = False
    dry_run: bool = True
    start_hour: int = Field(default=1, ge=0, le=23)
    end_hour: int = Field(default=6, ge=0, le=23)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=100)
    model_name: str = Field(default="qwen3.8:27b", min_length=1, max_length=200)
    retention_days: int = Field(default=30, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_hour == self.end_hour:
            raise ValueError("start_hour and end_hour must define a non-empty window")
        return self


class PhotoQuarantineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    photo_id: int
    status: str
    decision: str
    classification: str
    confidence: float
    reason: str
    preservation_flags: list
    first_result: dict
    verification_result: Optional[dict] = None
    model_name: str
    prompt_version: str
    original_path: str
    quarantine_path: Optional[str] = None
    content_hash: Optional[str] = None
    moved_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    deleted_confirmed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PhotoQuarantineListResponse(BaseModel):
    total: int
    items: list[PhotoQuarantineItemResponse]
