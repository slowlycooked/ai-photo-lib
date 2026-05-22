from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..models.project import Project
from ..schemas.project_search_settings import (
    ProjectSearchSettingsResponse,
    ProjectSearchSettingsUpdate,
)
from ..services.project_search_settings_service import (
    get_or_create_project_search_settings,
    reset_project_search_settings,
    update_project_search_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/search-settings", tags=["search-settings"])


@router.get("", response_model=ProjectSearchSettingsResponse)
def get_search_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectSearchSettingsResponse:
    """Return (or initialise) the search settings for a project."""
    row = get_or_create_project_search_settings(db, project_id)
    return ProjectSearchSettingsResponse.model_validate(row)


@router.put("", response_model=ProjectSearchSettingsResponse)
def update_search_settings(
    project_id: int,
    body: ProjectSearchSettingsUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectSearchSettingsResponse:
    """Update search settings for a project."""
    updates = body.model_dump(exclude_none=True)
    row = update_project_search_settings(db, project_id, updates)
    return ProjectSearchSettingsResponse.model_validate(row)


@router.post("/reset", response_model=ProjectSearchSettingsResponse)
def reset_search_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectSearchSettingsResponse:
    """Reset search settings to config defaults."""
    row = reset_project_search_settings(db, project_id)
    return ProjectSearchSettingsResponse.model_validate(row)
