from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_manager
from ..database import get_db
from ..models.project import Project
from ..schemas.project_ai import (
    ProjectAISettingsResponse,
    ProjectAISettingsUpdate,
)
from ..services.project_ai_service import (
    get_or_create_project_ai_settings,
)

_DEPRECATED_PROJECT_AI_SETTINGS_WRITE_MSG = (
    "Project-level AI model service configuration is deprecated. "
    "AI runtime is managed by global .env infrastructure settings."
)

router = APIRouter(prefix="/projects", tags=["projects-ai-settings"])


@router.get(
    "/{project_id}/ai-settings",
    response_model=ProjectAISettingsResponse,
    summary="Get effective AI runtime settings (read-only)",
    response_description="Effective AI runtime settings for this project. Backed by global .env defaults.",
)
def get_project_ai_settings(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return effective project AI settings (auto-provisioned from global defaults)."""
    return get_or_create_project_ai_settings(db, project.id)


@router.post(
    "/{project_id}/ai-settings/init",
    summary="Deprecated: initialize project AI service settings",
    responses={
        409: {
            "description": "Deprecated endpoint. Project-level AI service configuration is disabled.",
        }
    },
)
def init_project_ai_settings(
    project_id: int,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Deprecated: project-level AI service init is disabled."""
    raise HTTPException(status_code=409, detail=_DEPRECATED_PROJECT_AI_SETTINGS_WRITE_MSG)


@router.put(
    "/{project_id}/ai-settings",
    summary="Deprecated: update project AI service settings",
    responses={
        409: {
            "description": "Deprecated endpoint. Project-level AI service configuration is disabled.",
        }
    },
)
def update_project_ai_settings(
    project_id: int,
    body: ProjectAISettingsUpdate,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Deprecated: project-level AI service updates are disabled."""
    _ = (project_id, body, project, db)
    raise HTTPException(status_code=409, detail=_DEPRECATED_PROJECT_AI_SETTINGS_WRITE_MSG)
