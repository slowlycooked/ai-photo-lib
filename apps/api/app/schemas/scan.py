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
    inserted: int
    updated: int
    errors: int
    current_path: Optional[str] = None
    message: str
    recent_errors: list[str] = Field(default_factory=list)
    recent_files: list[ScanFileProgressEntry] = Field(default_factory=list)
