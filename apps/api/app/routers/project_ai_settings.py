from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..models.project import Project
from ..schemas.project_ai import (
    ProjectAISettingsResponse,
    ProjectAISettingsUpdate,
)
from ..services.project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    activate_prompt_template,
    get_project_ai_settings_strict,
    get_or_create_project_ai_settings,
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
    row = get_or_create_project_ai_settings(db, project_id)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_id}/ai-settings", response_model=ProjectAISettingsResponse)
def update_project_ai_settings(
    project_id: int,
    body: ProjectAISettingsUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Update AI settings for a project."""
    row = get_or_create_project_ai_settings(db, project_id)

    row.provider = body.provider
    row.endpoint_url = body.endpoint_url
    row.model_name = body.model_name
    row.temperature = body.temperature
    row.top_p = body.top_p
    row.max_tokens = body.max_tokens
    row.retry_count = body.retry_count
    row.output_language = body.output_language
    row.json_parse_strategy = body.json_parse_strategy
    row.updated_at = datetime.now()

    if body.active_prompt_template_id is not None:
        template = (
            db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.id == body.active_prompt_template_id,
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
            )
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        activate_prompt_template(db, project_id, template, task_type=TASK_IMAGE_ANALYSIS)

    db.commit()
    db.refresh(row)
    return row
