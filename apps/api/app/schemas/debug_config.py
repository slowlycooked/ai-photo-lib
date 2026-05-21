from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.debug_config import (
    DEBUG_MATRIX_FIELDS,
    build_preset_matrix,
    build_presets_map,
    normalize_debug_mode,
    normalize_log_level,
)


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class DebugMatrix(CamelModel):
    frontend_log_level: str = Field(...)
    backend_log_level: str = Field(...)
    ai_log_level: str = Field(...)
    search_log_level: str = Field(...)
    sql_log_level: str = Field(...)
    task_log_level: str = Field(...)

    @field_validator(*DEBUG_MATRIX_FIELDS, mode="before")
    @classmethod
    def validate_log_level(cls, value: object) -> str:
        return normalize_log_level(value)


class DebugConfigUpdate(CamelModel):
    debug_mode: str = Field(default="BASIC")
    debug_matrix: DebugMatrix = Field(default_factory=lambda: DebugMatrix(**build_preset_matrix("BASIC")))

    @field_validator("debug_mode", mode="before")
    @classmethod
    def validate_debug_mode(cls, value: object) -> str:
        return normalize_debug_mode(value)


class DebugConfig(DebugConfigUpdate):
    updated_at: Optional[datetime] = Field(default=None)


class DebugSettingsResponse(DebugConfig):
    presets: dict[str, DebugMatrix] = Field(
        default_factory=lambda: {
            mode: DebugMatrix(**matrix)
            for mode, matrix in build_presets_map().items()
        }
    )


class StoredDebugConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    debug_mode: str = Field(default="BASIC")
    debug_matrix: DebugMatrix = Field(default_factory=lambda: DebugMatrix(**build_preset_matrix("BASIC")))
    updated_at: Optional[datetime] = Field(default=None)


def build_default_debug_config(*, updated_at: Optional[datetime] = None) -> StoredDebugConfig:
    return StoredDebugConfig(
        debug_mode="BASIC",
        debug_matrix=DebugMatrix(**build_preset_matrix("BASIC")),
        updated_at=updated_at,
    )
