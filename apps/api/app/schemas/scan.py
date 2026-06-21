from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ScanFileProgressEntry(BaseModel):
    path: str
    status: str
    message: Optional[str] = None
    timestamp: str


class ScanStatus(BaseModel):
    task_id: Optional[int] = None
    running: bool
    scanned: int
    discovered_count: int = 0
    prepared_count: int = 0
    persisted_count: int = 0
    inserted: int
    updated: int
    errors: int
    current_stage: Optional[str] = None
    current_path: Optional[str] = None
    queue_depth: int = 0
    last_stage_latency_ms: Optional[int] = None
    message: str
    recent_errors: list[str] = Field(default_factory=list)
    recent_files: list[ScanFileProgressEntry] = Field(default_factory=list)
