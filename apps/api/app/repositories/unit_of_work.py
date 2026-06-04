from __future__ import annotations

from sqlalchemy.orm import Session

from .aijob_repository import AIJobRepository
from .embedding_repository import EmbeddingRepository
from .photo_repository import PhotoRepository
from .project_repository import ProjectRepository
from .prompt_template_repository import AISettingsRepository, PromptTemplateRepository


class UnitOfWork:
    """Aggregate repository access and transaction boundary.

    Usage::

        uow = UnitOfWork(db)
        project = uow.projects.get_active(project_id)
        photo = uow.photos.get_project_photo(project_id, photo_id)
        uow.commit()

    All repositories share the same ``db`` session so that a single
    ``commit()`` / ``rollback()`` covers all changes made within the unit.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self.projects = ProjectRepository(db)
        self.photos = PhotoRepository(db)
        self.ai_jobs = AIJobRepository(db)
        self.embeddings = EmbeddingRepository(db)
        self.prompt_templates = PromptTemplateRepository(db)
        self.ai_settings = AISettingsRepository(db)

    @property
    def db(self) -> Session:
        return self._db

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
