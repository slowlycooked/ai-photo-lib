from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.photo import Photo
from ..models.project import Project
from ..models.user import ProjectMembership, User
from ..schemas.user import CurrentUser
from ..services.auth_service import (
    SESSION_COOKIE_NAME,
    current_user_from_session,
    verify_session_cookie,
)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    """Resolve the authenticated user from the signed session cookie.

    The legacy env-based admin remains a bootstrap user until database users are
    created, so existing local deployments keep working after the migration.
    """
    session = verify_session_cookie(request.cookies.get(SESSION_COOKIE_NAME))
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    current = current_user_from_session(session)
    if current.id is None:
        if current.username == settings.auth_username and current.role == "admin":
            return current
        raise HTTPException(status_code=401, detail="Invalid session")

    row = (
        db.query(User)
        .filter(
            User.id == current.id,
            User.username == current.username,
            User.status == "active",
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=401, detail="User is disabled or no longer exists")
    return CurrentUser(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,  # type: ignore[arg-type]
        bootstrap=False,
    )


def require_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def _has_project_membership(
    db: Session,
    *,
    user: CurrentUser,
    project_id: int,
    manager: bool = False,
) -> bool:
    if user.role == "admin":
        return True
    if user.id is None:
        return False
    query = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == project_id,
        ProjectMembership.user_id == user.id,
    )
    if manager:
        query = query.filter(ProjectMembership.project_role == "manager")
    return query.first() is not None


def require_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Project:
    """FastAPI dependency: resolve project_id from path and assert the project is active."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not _has_project_membership(db, user=current_user, project_id=project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_project_manager(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Project:
    project = require_project(project_id, db, current_user)
    if not _has_project_membership(
        db,
        user=current_user,
        project_id=project_id,
        manager=True,
    ):
        raise HTTPException(status_code=403, detail="Project manager role required")
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
