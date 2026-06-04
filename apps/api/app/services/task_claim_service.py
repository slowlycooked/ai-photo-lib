from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from ..models.ai import AIJob
from ..models.project_task import ProjectTask

ClaimedTaskKind = Literal["project_task", "ai_job"]


@dataclass(frozen=True)
class ClaimedTask:
    kind: ClaimedTaskKind
    item: ProjectTask | AIJob


class TaskClaimService:
    """Centralize worker queue ordering and row locking."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def claim_next(self) -> ClaimedTask | None:
        project_task = self._claim_next_project_task()
        job = self._claim_next_ai_job()

        if project_task is None and job is None:
            return None
        if project_task is not None and (
            job is None or project_task.created_at <= job.created_at
        ):
            return ClaimedTask(kind="project_task", item=project_task)
        assert job is not None
        return ClaimedTask(kind="ai_job", item=job)

    def _claim_next_project_task(self) -> ProjectTask | None:
        return (
            self._db.query(ProjectTask)
            .filter(ProjectTask.status == "queued")
            .order_by(ProjectTask.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )

    def _claim_next_ai_job(self) -> AIJob | None:
        return (
            self._db.query(AIJob)
            .filter(AIJob.status == "queued")
            .order_by(AIJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
