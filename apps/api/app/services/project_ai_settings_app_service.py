from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..repositories.unit_of_work import UnitOfWork
from ..schemas.project_ai import ProjectAISettingsUpdate
from .project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    activate_prompt_template,
    get_or_create_project_ai_settings,
)


class PromptTemplateNotFoundError(RuntimeError):
    pass


class ProjectAISettingsAppService:
    """Application transaction boundary for project AI settings mutations."""

    def __init__(self, db: Session) -> None:
        self._uow = UnitOfWork(db)

    def init_settings(self, project_id: int) -> ProjectAISettings:
        try:
            row = get_or_create_project_ai_settings(self._uow.db, project_id)
            self._uow.commit()
            self._uow.db.refresh(row)
            return row
        except Exception:
            self._uow.rollback()
            raise

    def update_settings(
        self,
        *,
        project_id: int,
        body: ProjectAISettingsUpdate,
    ) -> ProjectAISettings:
        try:
            row = get_or_create_project_ai_settings(self._uow.db, project_id)

            row.provider = body.provider
            row.endpoint_url = body.endpoint_url
            row.model_name = body.model_name
            row.temperature = body.temperature
            row.top_p = body.top_p
            row.max_tokens = body.max_tokens
            row.retry_count = body.retry_count
            row.output_language = body.output_language
            row.json_parse_strategy = body.json_parse_strategy
            row.updated_at = datetime.now()

            if body.active_prompt_template_id is not None:
                template = self._find_prompt_template(
                    project_id=project_id,
                    template_id=body.active_prompt_template_id,
                )
                if not template:
                    raise PromptTemplateNotFoundError("Prompt template not found")
                activate_prompt_template(
                    self._uow.db,
                    project_id,
                    template,
                    task_type=TASK_IMAGE_ANALYSIS,
                )

            self._uow.commit()
            self._uow.db.refresh(row)
            return row
        except Exception:
            self._uow.rollback()
            raise

    def _find_prompt_template(
        self,
        *,
        project_id: int,
        template_id: int,
    ) -> ProjectPromptTemplate | None:
        return (
            self._uow.db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.id == template_id,
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
            )
            .first()
        )
