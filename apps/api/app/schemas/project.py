from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    photo_library_path: str
    thumbnail_path: Optional[str] = None
    is_default: bool = False

    @field_validator("photo_library_path")
    @classmethod
    def validate_library_path(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("photo_library_path must not be empty")
        # Must be absolute to prevent ambiguity
        if not v.startswith("/"):
            raise ValueError("photo_library_path must be an absolute path")
        # Prevent path traversal
        if os.path.normpath(v) != v:
            raise ValueError("photo_library_path must not contain '..'")
        return v


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    photo_library_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("photo_library_path")
    @classmethod
    def validate_library_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("photo_library_path must not be empty")
        if not v.startswith("/"):
            raise ValueError("photo_library_path must be an absolute path")
        if os.path.normpath(v) != v:
            raise ValueError("photo_library_path must not contain '..'")
        return v


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    photo_library_path: str
    thumbnail_path: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    total: int
    items: List[ProjectResponse]
