from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.project import Project
from ..schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
def list_projects(db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.deleted_at.is_(None))
        .order_by(Project.is_default.desc(), Project.created_at.asc())
        .all()
    )
    return ProjectListResponse(total=len(projects), items=projects)


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    # If this is being set as default, unset others
    if body.is_default:
        db.query(Project).filter(Project.deleted_at.is_(None)).update(
            {"is_default": False}
        )

    thumbnail = body.thumbnail_path or settings.thumbnail_path
    project = Project(
        name=body.name,
        description=body.description,
        photo_library_path=body.photo_library_path,
        thumbnail_path=thumbnail,
        is_default=body.is_default,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)
):
    project = _get_or_404(db, project_id)

    if body.is_default is True:
        db.query(Project).filter(
            Project.deleted_at.is_(None), Project.id != project_id
        ).update({"is_default": False})

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.photo_library_path is not None:
        project.photo_library_path = body.photo_library_path
    if body.thumbnail_path is not None:
        project.thumbnail_path = body.thumbnail_path
    if body.is_default is not None:
        project.is_default = body.is_default

    project.updated_at = datetime.now()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    if project.is_default:
        raise HTTPException(
            status_code=400, detail="Cannot delete the default project"
        )
    project.deleted_at = datetime.now()
    db.commit()


# ─── Helper ──────────────────────────────────────────────────────────────────
# NOTE: Prefer importing require_project from app.api.deps for new code.
# These helpers are retained for the CRUD endpoints above.


def _get_or_404(db: Session, project_id: int) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
