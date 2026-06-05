from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.deps import get_current_user, require_admin, require_project, require_project_manager
from ..database import get_db
from ..models.project import Project
from ..models.user import ProjectMembership
from ..schemas.user import CurrentUser
from ..schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from ..services.project_ai_service import (
    get_active_prompt_template_strict,
    resolve_project_ai_runtime_settings,
)
from ..services.project_embedding_settings_service import resolve_embedding_settings_strict
from ..services.project_scan_runtime_service import validate_project_library_path
from ..services.project_app_service import (
    DefaultProjectDeleteError,
    ProjectAppService,
    ProjectNotFoundError,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectReadinessCheck(BaseModel):
    name: str
    ready: bool
    message: str


class ProjectReadinessResponse(BaseModel):
    project_id: int
    ready: bool
    checks: list[ProjectReadinessCheck]


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
def list_projects(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    if current_user.role == "admin":
        projects = ProjectAppService(db).list_projects()
    elif current_user.id is None:
        projects = []
    else:
        projects = (
            db.query(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .filter(
                Project.deleted_at.is_(None),
                ProjectMembership.user_id == current_user.id,
            )
            .order_by(Project.is_default.desc(), Project.id.asc())
            .all()
        )
    return ProjectListResponse(total=len(projects), items=projects)


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    body: ProjectCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return ProjectAppService(db).create_project(body)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project: Project = Depends(require_project)):
    return project


@router.get("/{project_id}/readiness", response_model=ProjectReadinessResponse)
def get_project_readiness(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    checks: list[ProjectReadinessCheck] = []

    checks.append(_scan_readiness_check(project))

    try:
        ai_settings = resolve_project_ai_runtime_settings(db, project.id)
        get_active_prompt_template_strict(
            db,
            project.id,
            template_id=ai_settings.get("active_prompt_template_id"),
        )
        checks.append(
            ProjectReadinessCheck(
                name="ai_runtime",
                ready=True,
                message="Project AI settings and active prompt template are configured.",
            )
        )
    except RuntimeError as exc:
        checks.append(
            ProjectReadinessCheck(
                name="ai_runtime",
                ready=False,
                message=str(exc),
            )
        )

    try:
        resolve_embedding_settings_strict(db, project.id)
        checks.append(
            ProjectReadinessCheck(
                name="embedding_runtime",
                ready=True,
                message="Project embedding settings are configured.",
            )
        )
    except RuntimeError as exc:
        checks.append(
            ProjectReadinessCheck(
                name="embedding_runtime",
                ready=False,
                message=str(exc),
            )
        )

    return ProjectReadinessResponse(
        project_id=project.id,
        ready=all(check.ready for check in checks),
        checks=checks,
    )


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    _: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    try:
        return ProjectAppService(db).update_project(project_id, body)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: int,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        ProjectAppService(db).delete_project(project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DefaultProjectDeleteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ─── Helper ──────────────────────────────────────────────────────────────────
# NOTE: Prefer importing require_project from app.api.deps for new code.
# These helpers are retained for the CRUD endpoints above.


def _scan_readiness_check(project: Project) -> ProjectReadinessCheck:
    library_path = (project.photo_library_path or "").strip()
    thumb_path = (project.thumbnail_path or "").strip()

    library_error = validate_project_library_path(library_path)
    if library_error:
        return ProjectReadinessCheck(
            name="scan_runtime",
            ready=False,
            message=library_error,
        )

    if not thumb_path:
        return ProjectReadinessCheck(
            name="scan_runtime",
            ready=False,
            message="thumbnail_path is empty.",
        )

    thumb = Path(thumb_path).expanduser().resolve()
    if not thumb.exists() or not thumb.is_dir():
        return ProjectReadinessCheck(
            name="scan_runtime",
            ready=False,
            message=f"thumbnail_path not found or not a directory: {thumb}",
        )

    if not os.access(str(thumb), os.W_OK | os.X_OK):
        return ProjectReadinessCheck(
            name="scan_runtime",
            ready=False,
            message=f"thumbnail_path is not writable: {thumb}",
        )

    return ProjectReadinessCheck(
        name="scan_runtime",
        ready=True,
        message="Project scan paths are valid and writable.",
    )
