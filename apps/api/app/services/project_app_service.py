from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models.project import Project
from ..repositories.project_repository import ProjectRepository
from ..schemas.project import ProjectCreate, ProjectUpdate

logger = logging.getLogger(__name__)


class ProjectNotFoundError(RuntimeError):
    pass


class DefaultProjectDeleteError(RuntimeError):
    pass


def repair_legacy_project_library_paths(db: Session) -> int:
    """Rewrite legacy container-style project paths to the current host path.

    Older databases stored project roots under the legacy ``/photos`` prefix.
    Newer environments keep the authoritative host path in ``PHOTO_LIBRARY_PATH``.
    This repair is intentionally narrow and only touches legacy-prefixed rows.
    """
    legacy_prefix = "/photos"
    configured_root = (settings.photo_library_path or "").strip().rstrip("/")
    if not configured_root:
        return 0

    repaired = 0
    projects = (
        db.query(Project)
        .filter(Project.deleted_at.is_(None))
        .filter(Project.photo_library_path.like(f"{legacy_prefix}%"))
        .all()
    )
    for project in projects:
        legacy_path = (project.photo_library_path or "").strip()
        if not legacy_path.startswith(legacy_prefix):
            continue
        suffix = legacy_path[len(legacy_prefix) :]
        project.photo_library_path = configured_root + suffix
        repaired += 1

    if repaired:
        db.commit()
        logger.warning(
            "Repaired %d legacy project photo_library_path value(s) using configured PHOTO_LIBRARY_PATH=%s",
            repaired,
            configured_root,
        )

    return repaired


@dataclass
class ProjectAppService:
    db: Session

    def __post_init__(self) -> None:
        self._repo = ProjectRepository(self.db)

    def list_projects(self) -> list[Project]:
        return self._repo.list_active()

    def get_project(self, project_id: int) -> Project:
        project = self._repo.get_active(project_id)
        if project is None:
            raise ProjectNotFoundError("Project not found")
        return project

    def create_project(self, body: ProjectCreate) -> Project:
        thumbnail_path = body.thumbnail_path or settings.thumbnail_path
        project = self._repo.create(
            name=body.name,
            description=body.description,
            photo_library_path=body.photo_library_path,
            thumbnail_path=thumbnail_path,
            is_default=body.is_default,
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def update_project(self, project_id: int, body: ProjectUpdate) -> Project:
        project = self.get_project(project_id)
        self._repo.update(
            project,
            name=body.name,
            description=body.description,
            photo_library_path=body.photo_library_path,
            thumbnail_path=body.thumbnail_path,
            is_default=body.is_default,
            updated_at=datetime.now(),
        )
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete_project(self, project_id: int) -> None:
        project = self.get_project(project_id)
        if project.is_default:
            raise DefaultProjectDeleteError("Cannot delete the default project")
        self._repo.soft_delete(project)
        self.db.commit()