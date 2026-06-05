from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from ..models.ai import AIJob
from ..models.project_task import ProjectTask

ClaimedTaskKind = Literal["project_task", "ai_job"]


@dataclass(frozen=True)
class ClaimedTask:
    kind: ClaimedTaskKind
    item: ProjectTask | AIJob


@dataclass(frozen=True)
class _QueueCandidate:
    kind: ClaimedTaskKind
    id: int
    created_at: datetime


class TaskClaimService:
    """Centralize worker queue ordering and row locking."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def claim_next(self) -> ClaimedTask | None:
        candidates = sorted(
            [
                candidate
                for candidate in (
                    self._peek_next_project_task(),
                    self._peek_next_ai_job(),
                )
                if candidate is not None
            ],
            key=lambda candidate: candidate.created_at,
        )

        for candidate in candidates:
            if candidate.kind == "project_task":
                project_task = self._claim_project_task(candidate.id)
                if project_task is not None:
                    return ClaimedTask(kind="project_task", item=project_task)
                continue

            job = self._claim_ai_job(candidate.id)
            if job is not None:
                return ClaimedTask(kind="ai_job", item=job)

        return None

    def _peek_next_project_task(self) -> _QueueCandidate | None:
        row = (
            self._db.query(ProjectTask.id, ProjectTask.created_at)
            .filter(ProjectTask.status == "queued")
            .order_by(ProjectTask.created_at)
            .first()
        )
        if row is None:
            return None
        return _QueueCandidate(kind="project_task", id=row.id, created_at=row.created_at)

    def _peek_next_ai_job(self) -> _QueueCandidate | None:
        row = (
            self._db.query(AIJob.id, AIJob.created_at)
            .filter(AIJob.status == "queued")
            .order_by(AIJob.created_at)
            .first()
        )
        if row is None:
            return None
        return _QueueCandidate(kind="ai_job", id=row.id, created_at=row.created_at)

    def _claim_project_task(self, task_id: int) -> ProjectTask | None:
        return (
            self._db.query(ProjectTask)
            .filter(ProjectTask.id == task_id, ProjectTask.status == "queued")
            .with_for_update(skip_locked=True)
            .first()
        )

    def _claim_ai_job(self, job_id: int) -> AIJob | None:
        return (
            self._db.query(AIJob)
            .filter(AIJob.id == job_id, AIJob.status == "queued")
            .with_for_update(skip_locked=True)
            .first()
        )
