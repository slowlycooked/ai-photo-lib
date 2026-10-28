from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.project import Project
from ..models.project_library_path import ProjectLibraryPath
from ..schemas.project import ProjectResponse
from .library_path_rules import normalize_library_paths


class EmptyLibraryPathsError(ValueError):
    """Raised when a project would be left without any library path."""


def get_project_library_paths(db: Session, project: Project) -> list[str]:
    """Return the project's library roots ordered by position (read-only).

    Falls back to the legacy ``projects.photo_library_path`` column when the
    child table has not been populated yet (pre-migration rows).
    """
    rows = (
        db.query(ProjectLibraryPath)
        .filter(ProjectLibraryPath.project_id == project.id)
        .order_by(ProjectLibraryPath.position.asc(), ProjectLibraryPath.id.asc())
        .all()
    )
    if rows:
        return [row.path for row in rows]
    legacy = (project.photo_library_path or "").strip()
    return [legacy] if legacy else []


def sync_project_library_paths(db: Session, project: Project, paths: list[str]) -> list[str]:
    """Replace the project's library path set and mirror the primary column.

    ``paths[0]`` becomes both position 0 and ``projects.photo_library_path``.
    """
    normalized = normalize_library_paths(paths)

    db.query(ProjectLibraryPath).filter(
        ProjectLibraryPath.project_id == project.id
    ).delete(synchronize_session=False)
    for position, path in enumerate(normalized):
        db.add(ProjectLibraryPath(project_id=project.id, path=path, position=position))

    project.photo_library_path = normalized[0]
    db.flush()
    return normalized


def build_project_response(db: Session, project: Project) -> ProjectResponse:
    """Serialize a project ORM row including the full library path list."""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        photo_library_path=project.photo_library_path,
        photo_library_paths=get_project_library_paths(db, project),
        thumbnail_path=project.thumbnail_path,
        is_default=project.is_default,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
