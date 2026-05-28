from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..models.photo import Photo
from ..repositories.prompt_template_repository import PromptTemplateRepository
from ..schemas.project_ai import PromptTemplateCreate, PromptTemplateUpdate
from .project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    activate_prompt_template,
    build_default_template,
    default_output_schema,
)


class PromptTemplateNotFoundError(RuntimeError):
    pass


class ActivePromptTemplateDeleteError(RuntimeError):
    pass


@dataclass
class ProjectPromptTemplatesAppService:
    db: Session

    def __post_init__(self) -> None:
        self._repo = PromptTemplateRepository(self.db)

    def list_templates(self, *, project_id: int, task_type: str) -> list[ProjectPromptTemplate]:
        return (
            self.db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == task_type,
            )
            .order_by(ProjectPromptTemplate.version.desc(), ProjectPromptTemplate.id.desc())
            .all()
        )

    def create_template(
        self,
        *,
        project_id: int,
        body: PromptTemplateCreate,
    ) -> ProjectPromptTemplate:
        latest = (
            self.db.query(func.max(ProjectPromptTemplate.version))
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == body.task_type,
            )
            .scalar()
        )
        next_version = (latest or 0) + 1

        template = ProjectPromptTemplate(
            project_id=project_id,
            name=body.name,
            task_type=body.task_type,
            system_prompt=body.system_prompt,
            user_prompt=body.user_prompt,
            output_schema=body.output_schema or default_output_schema(),
            is_active=False,
            version=next_version,
        )
        self._repo.create(template)

        if body.is_active:
            activate_prompt_template(self.db, project_id, template, task_type=body.task_type)

        self.db.commit()
        self.db.refresh(template)
        return template

    def update_template(
        self,
        *,
        project_id: int,
        template_id: int,
        body: PromptTemplateUpdate,
    ) -> ProjectPromptTemplate:
        current = self._repo.get(project_id, template_id)
        if current is None:
            raise PromptTemplateNotFoundError("Prompt template not found")

        next_version = (
            self.db.query(func.max(ProjectPromptTemplate.version))
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == current.task_type,
            )
            .scalar()
            or 0
        ) + 1

        new_template = ProjectPromptTemplate(
            project_id=project_id,
            name=body.name or current.name,
            task_type=current.task_type,
            system_prompt=(
                body.system_prompt
                if body.system_prompt is not None
                else current.system_prompt
            ),
            user_prompt=body.user_prompt,
            output_schema=body.output_schema or current.output_schema or default_output_schema(),
            is_active=False,
            version=next_version,
        )
        self._repo.create(new_template)
        if body.is_active:
            activate_prompt_template(self.db, project_id, new_template, task_type=current.task_type)

        self.db.commit()
        self.db.refresh(new_template)
        return new_template

    def delete_template(self, *, project_id: int, template_id: int) -> None:
        template = self._repo.get(project_id, template_id)
        if template is None:
            raise PromptTemplateNotFoundError("Prompt template not found")

        settings_row = (
            self.db.query(ProjectAISettings)
            .filter(ProjectAISettings.project_id == project_id)
            .first()
        )
        if template.is_active or (
            settings_row is not None and settings_row.active_prompt_template_id == template.id
        ):
            raise ActivePromptTemplateDeleteError("Cannot delete active prompt template")

        self._repo.delete(template)
        self.db.commit()

    def reset_default_template(self, *, project_id: int) -> ProjectPromptTemplate:
        next_version = (
            self.db.query(func.max(ProjectPromptTemplate.version))
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
            )
            .scalar()
            or 0
        ) + 1

        base = build_default_template(project_id)
        template = ProjectPromptTemplate(
            project_id=project_id,
            name=f"默认图片分析模板 v{next_version}",
            task_type=TASK_IMAGE_ANALYSIS,
            system_prompt=base.system_prompt,
            user_prompt=base.user_prompt,
            output_schema=base.output_schema,
            is_active=False,
            version=next_version,
        )
        self._repo.create(template)
        activate_prompt_template(self.db, project_id, template, task_type=TASK_IMAGE_ANALYSIS)

        self.db.commit()
        self.db.refresh(template)
        return template

    def get_project_photo(self, *, project_id: int, photo_id: int) -> Photo | None:
        return (
            self.db.query(Photo)
            .filter(Photo.id == photo_id, Photo.project_id == project_id)
            .first()
        )