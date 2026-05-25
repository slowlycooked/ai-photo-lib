from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..models.project import Project
from ..schemas.face import ProjectFaceSettingsResponse, ProjectFaceSettingsUpdate
from ..services.project_face_settings_service import (
    get_or_create_project_face_settings,
    reset_project_face_settings,
    update_project_face_settings,
)

router = APIRouter(prefix="/projects/{project_id}/face-settings", tags=["face-settings"])


@router.get("", response_model=ProjectFaceSettingsResponse)
def get_face_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectFaceSettingsResponse:
    row = get_or_create_project_face_settings(db, project_id)
    return ProjectFaceSettingsResponse.model_validate(row)


@router.put("", response_model=ProjectFaceSettingsResponse)
def put_face_settings(
    project_id: int,
    body: ProjectFaceSettingsUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectFaceSettingsResponse:
    updates = body.model_dump(exclude_none=True)
    row = update_project_face_settings(db, project_id, updates)
    return ProjectFaceSettingsResponse.model_validate(row)


@router.post("/reset", response_model=ProjectFaceSettingsResponse)
def post_reset_face_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectFaceSettingsResponse:
    row = reset_project_face_settings(db, project_id)
    return ProjectFaceSettingsResponse.model_validate(row)
