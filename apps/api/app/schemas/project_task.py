from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    task_type: str
    status: str
    retry_count: int
    request_params: Optional[dict[str, Any]] = None
    progress_payload: Optional[dict[str, Any]] = None
    result_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    recent_errors: list[str] = Field(default_factory=list)
    failure_count: int = 0
    latest_failure: Optional["ProjectTaskFailureDetail"] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProjectTaskFailureDetail(BaseModel):
    key: str
    source: str
    message: str
    path: Optional[str] = None
    status: Optional[str] = None
    timestamp: Optional[datetime] = None
    details: Optional[dict[str, Any]] = None


class ProjectTaskFailureListResponse(BaseModel):
    total: int
    items: list[ProjectTaskFailureDetail]


class ProjectTaskListResponse(BaseModel):
    total: int
    items: list[ProjectTaskResponse]
