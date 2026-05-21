from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.photo import Photo
from ..models.project import Project


def require_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    """FastAPI dependency: resolve project_id from path and assert the project is active."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_project_photo(
    project_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
) -> Photo:
    """FastAPI dependency: resolve a photo scoped to the given project."""
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found in project")
    return photo
