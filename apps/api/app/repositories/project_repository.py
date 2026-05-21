from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.project import Project


class ProjectRepository:
    """Write-side repository for Project entities.

    All queries are explicitly scoped by project state (active / soft-deleted).
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── reads ─────────────────────────────────────────────────────────────────

    def get_active(self, project_id: int) -> Optional[Project]:
        """Return an active (non-deleted) project, or None."""
        return (
            self._db.query(Project)
            .filter(Project.id == project_id, Project.deleted_at.is_(None))
            .first()
        )

    def list_active(self) -> list[Project]:
        """Return all active projects ordered by default-first, then creation time."""
        return (
            self._db.query(Project)
            .filter(Project.deleted_at.is_(None))
            .order_by(Project.is_default.desc(), Project.created_at.asc())
            .all()
        )

    # ── writes ────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        name: str,
        photo_library_path: str,
        thumbnail_path: str,
        description: Optional[str] = None,
        is_default: bool = False,
    ) -> Project:
        """Create and persist a new project."""
        if is_default:
            self._unset_all_defaults()

        project = Project(
            name=name,
            description=description,
            photo_library_path=photo_library_path,
            thumbnail_path=thumbnail_path,
            is_default=is_default,
        )
        self._db.add(project)
        self._db.flush()
        return project

    def update(self, project: Project, **fields: object) -> Project:
        """Apply partial field updates to an existing project."""
        if fields.get("is_default") is True:
            self._unset_all_defaults(exclude_id=project.id)

        for key, value in fields.items():
            if value is not None:
                setattr(project, key, value)

        project.updated_at = datetime.now()
        self._db.flush()
        return project

    def soft_delete(self, project: Project) -> None:
        """Mark a project as deleted (soft delete)."""
        project.deleted_at = datetime.now()
        self._db.flush()

    # ── private helpers ───────────────────────────────────────────────────────

    def _unset_all_defaults(self, *, exclude_id: Optional[int] = None) -> None:
        q = self._db.query(Project).filter(Project.deleted_at.is_(None))
        if exclude_id is not None:
            q = q.filter(Project.id != exclude_id)
        q.update({"is_default": False})
