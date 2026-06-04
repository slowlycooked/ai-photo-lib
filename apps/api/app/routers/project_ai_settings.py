from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.project_ai import (
    ProjectAISettingsResponse,
    ProjectAISettingsUpdate,
)
from ..services.project_ai_settings_app_service import (
    ProjectAISettingsAppService,
    PromptTemplateNotFoundError,
)
from ..services.project_ai_service import (
    get_project_ai_settings_strict,
)

router = APIRouter(prefix="/projects", tags=["projects-ai-settings"])


@router.get("/{project_id}/ai-settings", response_model=ProjectAISettingsResponse)
def get_project_ai_settings(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return strict project AI settings (no implicit default creation)."""
    try:
        row = get_project_ai_settings_strict(db, project.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return row


@router.post("/{project_id}/ai-settings/init", response_model=ProjectAISettingsResponse)
def init_project_ai_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Explicitly initialize project AI settings and default prompt template."""
    return ProjectAISettingsAppService(db).init_settings(project_id)


@router.put("/{project_id}/ai-settings", response_model=ProjectAISettingsResponse)
def update_project_ai_settings(
    project_id: int,
    body: ProjectAISettingsUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Update AI settings for a project."""
    try:
        return ProjectAISettingsAppService(db).update_settings(
            project_id=project_id,
            body=body,
        )
    except PromptTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
