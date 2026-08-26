from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

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
    content_rating: Literal["SAFE", "SENSITIVE", "ADULT"] = "SAFE"
    sensitive_content_flags: list[str] = Field(default_factory=list)
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
    human_label: Optional[Literal["KEEP", "TRASH"]] = None
    human_label_note: Optional[str] = None
    human_labeled_by: Optional[str] = None
    human_labeled_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PhotoQuarantineListResponse(BaseModel):
    total: int
    items: list[PhotoQuarantineItemResponse]


class PhotoQuarantineRunRequest(BaseModel):
    retry_failed: bool = False


class PhotoQuarantineBatchRequest(BaseModel):
    action: Literal[
        "KEEP",
        "REQUEST_DELETE",
        "MOVE",
        "RESTORE",
        "RETRY_ANALYSIS",
        "LABEL_KEEP",
        "LABEL_TRASH",
    ]
    item_ids: list[int] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_unique_item_ids(self):
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("item_ids must not contain duplicates")
        return self


class PhotoQuarantineBatchItemResponse(BaseModel):
    item_id: int
    succeeded: bool
    item: Optional[PhotoQuarantineItemResponse] = None
    error_code: Optional[str] = None
    message: Optional[str] = None


class PhotoQuarantineBatchResponse(BaseModel):
    requested: int
    succeeded: int
    failed: int
    results: list[PhotoQuarantineBatchItemResponse]


class PhotoQuarantineReconciliationResponse(BaseModel):
    checked: int
    confirmed: int
    remaining: int
    failed: int


class PhotoQuarantineLabelRequest(BaseModel):
    label: Literal["KEEP", "TRASH"]
    note: Optional[str] = Field(default=None, max_length=2000)


class PhotoQuarantineCalibrationCategory(BaseModel):
    classification: str
    labeled_total: int
    human_keep: int
    human_trash: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


class PhotoQuarantineCalibrationResponse(BaseModel):
    labeled_total: int
    human_keep: int
    human_trash: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: Optional[float] = None
    recall: Optional[float] = None
    false_positive_rate: Optional[float] = None
    target_sample_size: int
    minimum_per_label: int
    sample_target_met: bool
    class_balance_met: bool
    zero_false_positive_met: bool
    ready_for_auto_move: bool
    categories: list[PhotoQuarantineCalibrationCategory]
