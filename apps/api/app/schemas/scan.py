from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ScanStatus(BaseModel):
    running: bool
    scanned: int
    inserted: int
    updated: int
    errors: int
    current_path: Optional[str] = None
    message: str
