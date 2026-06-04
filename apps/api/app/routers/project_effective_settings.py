from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..models.project import Project
from ..schemas.project_effective_settings import ProjectEffectiveSettingsResponse
from ..services.search.settings_resolver import SearchSettingsResolver

router = APIRouter(prefix="/projects", tags=["project-effective-settings"])


@router.get(
    "/{project_id}/settings/effective",
    response_model=ProjectEffectiveSettingsResponse,
)
def get_effective_project_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectEffectiveSettingsResponse:
    """Return resolved project settings with per-field source metadata."""
    return ProjectEffectiveSettingsResponse.model_validate(
        SearchSettingsResolver.resolve_effective_with_sources(db, project_id)
    )
