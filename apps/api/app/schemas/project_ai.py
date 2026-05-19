from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectAISettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    provider: str
    endpoint_url: str
    model_name: str
    temperature: float
    top_p: float
    max_tokens: int
    retry_count: int
    output_language: str
    json_parse_strategy: str
    active_prompt_template_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ProjectAISettingsUpdate(BaseModel):
    provider: str = "llama-server"
    endpoint_url: str
    model_name: str
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=0.8, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=1, le=32768)
    retry_count: int = Field(default=1, ge=0, le=10)
    output_language: str = "中文"
    json_parse_strategy: str = "auto_extract"
    active_prompt_template_id: Optional[int] = None


class PromptTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    task_type: str
    system_prompt: Optional[str] = None
    user_prompt: str
    output_schema: Optional[dict[str, Any]] = None
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class PromptTemplateListResponse(BaseModel):
    total: int
    items: list[PromptTemplateResponse]


class PromptTemplateCreate(BaseModel):
    name: str
    task_type: str = "image_analysis"
    system_prompt: Optional[str] = None
    user_prompt: str
    output_schema: Optional[dict[str, Any]] = None
    is_active: bool = True


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: str
    output_schema: Optional[dict[str, Any]] = None
    is_active: bool = True


class PromptTemplateTestRequest(BaseModel):
    image_id: int
    prompt_template_id: Optional[int] = None
    override_prompt: Optional[str] = None


class PromptTemplateTestResponse(BaseModel):
    success: bool
    raw_output: str
    parsed_json: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    retryable: Optional[bool] = None
    error_code: Optional[str] = None
    duration_ms: int
