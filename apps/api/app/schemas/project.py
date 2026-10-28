from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ..services.library_path_rules import normalize_library_path, normalize_library_paths


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    photo_library_path: Optional[str] = None
    photo_library_paths: Optional[List[str]] = None
    thumbnail_path: Optional[str] = None
    is_default: bool = False

    @field_validator("photo_library_path")
    @classmethod
    def validate_library_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_library_path(v)

    @field_validator("photo_library_paths")
    @classmethod
    def validate_library_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return normalize_library_paths(v)

    @model_validator(mode="after")
    def _resolve_library_paths(self) -> "ProjectCreate":
        if self.photo_library_paths is None and self.photo_library_path is None:
            raise ValueError("photo_library_path is required")
        if (
            self.photo_library_paths is not None
            and self.photo_library_path is not None
            and self.photo_library_paths[0] != self.photo_library_path
        ):
            raise ValueError(
                "photo_library_path must match photo_library_paths[0] when both are provided"
            )
        return self

    def effective_library_paths(self) -> List[str]:
        if self.photo_library_paths is not None:
            return list(self.photo_library_paths)
        if self.photo_library_path is None:
            raise ValueError("photo_library_path is required")
        return [self.photo_library_path]


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    photo_library_path: Optional[str] = None
    photo_library_paths: Optional[List[str]] = None
    thumbnail_path: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("photo_library_path")
    @classmethod
    def validate_library_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_library_path(v)

    @field_validator("photo_library_paths")
    @classmethod
    def validate_library_paths(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        return normalize_library_paths(v)

    @model_validator(mode="after")
    def _check_library_path_consistency(self) -> "ProjectUpdate":
        if (
            self.photo_library_paths is not None
            and self.photo_library_path is not None
            and self.photo_library_paths[0] != self.photo_library_path
        ):
            raise ValueError(
                "photo_library_path must match photo_library_paths[0] when both are provided"
            )
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    photo_library_path: str
    photo_library_paths: List[str] = []
    thumbnail_path: Optional[str] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    total: int
    items: List[ProjectResponse]
