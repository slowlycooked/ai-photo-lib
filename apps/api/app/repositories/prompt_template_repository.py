from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models.ai import ProjectAISettings, ProjectPromptTemplate


class PromptTemplateRepository:
    """Write-side repository for ProjectPromptTemplate entities."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, project_id: int, template_id: int) -> Optional[ProjectPromptTemplate]:
        return (
            self._db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.id == template_id,
            )
            .first()
        )

    def get_active(self, project_id: int, task_type: str) -> Optional[ProjectPromptTemplate]:
        return (
            self._db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == task_type,
                ProjectPromptTemplate.is_active.is_(True),
            )
            .first()
        )

    def list_for_project(
        self,
        project_id: int,
        task_type: Optional[str] = None,
    ) -> list[ProjectPromptTemplate]:
        q = self._db.query(ProjectPromptTemplate).filter(
            ProjectPromptTemplate.project_id == project_id
        )
        if task_type:
            q = q.filter(ProjectPromptTemplate.task_type == task_type)
        return q.order_by(ProjectPromptTemplate.id.desc()).all()

    # ── writes ────────────────────────────────────────────────────────────────

    def deactivate_all(self, project_id: int, task_type: str) -> None:
        """Deactivate all templates for a project/task. Used before activating a new one."""
        self._db.query(ProjectPromptTemplate).filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == task_type,
        ).update({"is_active": False})

    def create(self, template: ProjectPromptTemplate) -> ProjectPromptTemplate:
        self._db.add(template)
        self._db.flush()
        return template

    def update(self, template: ProjectPromptTemplate, **fields: object) -> ProjectPromptTemplate:
        for key, value in fields.items():
            setattr(template, key, value)
        template.updated_at = datetime.now(timezone.utc)
        self._db.flush()
        return template

    def delete(self, template: ProjectPromptTemplate) -> None:
        self._db.delete(template)
        self._db.flush()


class AISettingsRepository:
    """Repository for ProjectAISettings (one per project)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, project_id: int) -> Optional[ProjectAISettings]:
        return (
            self._db.query(ProjectAISettings)
            .filter(ProjectAISettings.project_id == project_id)
            .first()
        )

    def upsert(self, settings: ProjectAISettings) -> ProjectAISettings:
        existing = self.get(settings.project_id)
        if existing is None:
            self._db.add(settings)
            self._db.flush()
            return settings
        for col in (
            "provider",
            "endpoint_url",
            "model_name",
            "temperature",
            "top_p",
            "max_tokens",
            "retry_count",
            "output_language",
            "json_parse_strategy",
            "active_prompt_template_id",
        ):
            val = getattr(settings, col, None)
            if val is not None:
                setattr(existing, col, val)
        existing.updated_at = datetime.now(timezone.utc)
        self._db.flush()
        return existing
