from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..models.project import Project
from ..repositories.project_repository import ProjectRepository
from ..schemas.project import ProjectCreate, ProjectUpdate


class ProjectNotFoundError(RuntimeError):
    pass


class DefaultProjectDeleteError(RuntimeError):
    pass


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