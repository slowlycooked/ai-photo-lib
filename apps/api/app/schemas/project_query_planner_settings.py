"""Pydantic schemas for project query planner settings."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectQueryPlannerSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    ai_service_profile_id: Optional[int] = None
    enabled: bool
    provider: str
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    temperature: float
    top_p: float
    max_tokens: int
    timeout_seconds: int
    json_parse_strategy: str
    planner_version: str
    prompt_template: Optional[str] = None
    system_prompt: Optional[str] = None
    fallback_mode: str
    created_at: datetime
    updated_at: datetime


class ProjectQueryPlannerSettingsUpdate(BaseModel):
    ai_service_profile_id: Optional[int] = None
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=4096)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=120)
    json_parse_strategy: Optional[str] = None
    planner_version: Optional[str] = None
    prompt_template: Optional[str] = None
    system_prompt: Optional[str] = None
    fallback_mode: Optional[str] = None


class QueryPlannerTestRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)


class QueryPlannerTestResponse(BaseModel):
    query: str
    planner_debug: dict
    parsed_query_plan: dict
