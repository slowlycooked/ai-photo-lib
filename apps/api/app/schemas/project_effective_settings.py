"""Pydantic schemas for read-only effective project settings."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EffectiveSettingValue(BaseModel):
    value: Any
    source: str


class ProjectEffectiveSettingsResponse(BaseModel):
    search: dict[str, EffectiveSettingValue]
    ai: dict[str, dict[str, EffectiveSettingValue]] = {}
