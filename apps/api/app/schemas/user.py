from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SystemRole = Literal["admin", "project_manager", "viewer"]
ProjectRole = Literal["manager", "viewer"]
AICapability = Literal["vision", "embedding", "query_planner"]


class CurrentUser(BaseModel):
    id: Optional[int] = None
    username: str
    display_name: Optional[str] = None
    role: SystemRole
    bootstrap: bool = False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuthSessionResponse(BaseModel):
    user_id: Optional[int] = None
    username: str
    display_name: Optional[str] = None
    role: SystemRole
    capabilities: list[str]
    sessionTimeoutMinutes: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: Optional[str] = None
    role: SystemRole
    status: str
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    total: int
    items: list[UserResponse]


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=256)
    display_name: Optional[str] = None
    role: SystemRole = "viewer"
    status: str = "active"


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[SystemRole] = None
    status: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=256)


class ProjectMembershipResponse(BaseModel):
    id: int
    project_id: int
    user_id: int
    username: str
    display_name: Optional[str] = None
    project_role: ProjectRole
    created_at: datetime
    updated_at: datetime


class ProjectMembershipListResponse(BaseModel):
    total: int
    items: list[ProjectMembershipResponse]


class ProjectMembershipUpsert(BaseModel):
    user_id: int
    project_role: ProjectRole = "viewer"


class UserProjectAccessResponse(BaseModel):
    project_id: int
    project_name: str
    project_description: Optional[str] = None
    project_role: ProjectRole
    created_at: datetime
    updated_at: datetime


class UserProjectAccessListResponse(BaseModel):
    total: int
    items: list[UserProjectAccessResponse]


class UserProjectAccessUpsert(BaseModel):
    project_role: ProjectRole = "viewer"


class AIServiceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capability: AICapability
    provider: str
    endpoint_url: Optional[str] = None
    has_api_key: bool = False
    model_name: str
    model_params_json: Optional[dict[str, Any]] = None
    timeout_seconds: int
    enabled: bool
    visible_to_projects: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class AIServiceProfileListResponse(BaseModel):
    total: int
    items: list[AIServiceProfileResponse]


class AIServiceProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    capability: AICapability
    provider: str = "openai-compatible"
    endpoint_url: str
    api_key: Optional[str] = None
    model_name: str
    model_params_json: Optional[dict[str, Any]] = None
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    enabled: bool = True
    visible_to_projects: bool = True
    is_default: bool = False


class AIServiceProfileUpdate(BaseModel):
    name: Optional[str] = None
    capability: Optional[AICapability] = None
    provider: Optional[str] = None
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    model_params_json: Optional[dict[str, Any]] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=600)
    enabled: Optional[bool] = None
    visible_to_projects: Optional[bool] = None
    is_default: Optional[bool] = None
