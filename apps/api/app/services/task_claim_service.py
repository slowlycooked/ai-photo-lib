from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from typing import Literal, Optional

from ..config import settings
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

    def __init__(
        self,
        db: Session,
        *,
        worker_id: Optional[str] = None,
        lease_seconds: Optional[int] = None,
    ) -> None:
        self._db = db
        self._worker_id = worker_id or f"worker-{os.getpid()}"
        # Reuse existing timeout settings to avoid introducing new config keys.
        base_timeout = max(int(settings.embedding_timeout_seconds or 60), 180)
        self._lease_seconds = int(lease_seconds or (base_timeout * 4))

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
                    self._mark_project_task_claimed(project_task)
                    self._db.commit()
                    return ClaimedTask(kind="project_task", item=project_task)
                continue

            job = self._claim_ai_job(candidate.id)
            if job is not None:
                self._mark_ai_job_claimed(job)
                self._db.commit()
                return ClaimedTask(kind="ai_job", item=job)

        return None

    def recover_stuck_running_tasks(self) -> dict[str, int]:
        now = datetime.utcnow()
        recovered_project_tasks = 0
        recovered_ai_jobs = 0

        running_project_tasks = (
            self._db.query(ProjectTask)
            .filter(
                ProjectTask.status == "running",
            )
            .all()
        )
        for task in running_project_tasks:
            if not _lease_expired(task.lease_expires_at, now):
                continue
            task.status = "failed"
            task.error_message = "Task lease expired while running"
            task.finished_at = now
            task.updated_at = now
            task.locked_by = None
            task.locked_at = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            task.last_error_code = "lease_expired"
            task.last_error_at = now
            recovered_project_tasks += 1

        running_ai_jobs = (
            self._db.query(AIJob)
            .filter(
                AIJob.status == "running",
            )
            .all()
        )
        for job in running_ai_jobs:
            if not _lease_expired(job.lease_expires_at, now):
                continue
            job.retry_count = int(job.retry_count or 0) + 1
            job.error_message = "Task lease expired while running"
            job.parse_error = "Task lease expired while running"
            job.finished_at = now
            job.updated_at = now
            job.locked_by = None
            job.locked_at = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            job.last_error_code = "lease_expired"
            job.last_error_at = now
            if job.retry_count < int(settings.ai_max_retries):
                job.status = "queued"
            else:
                job.status = "failed"
            recovered_ai_jobs += 1

        if recovered_project_tasks or recovered_ai_jobs:
            self._db.commit()

        return {
            "project_tasks": recovered_project_tasks,
            "ai_jobs": recovered_ai_jobs,
        }

    def touch_project_task_lease(self, task: ProjectTask) -> None:
        now = datetime.utcnow()
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        task.updated_at = now
        self._db.flush()

    def touch_ai_job_lease(self, job: AIJob) -> None:
        now = datetime.utcnow()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        job.updated_at = now
        self._db.flush()

    def _mark_project_task_claimed(self, task: ProjectTask) -> None:
        now = datetime.utcnow()
        task.status = "running"
        if task.started_at is None:
            task.started_at = now
        task.updated_at = now
        task.locked_by = self._worker_id
        task.locked_at = now
        task.heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        task.last_error_code = None

    def _mark_ai_job_claimed(self, job: AIJob) -> None:
        now = datetime.utcnow()
        job.status = "running"
        if job.started_at is None:
            job.started_at = now
        job.updated_at = now
        job.locked_by = self._worker_id
        job.locked_at = now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self._lease_seconds)
        job.last_error_code = None

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


def _lease_expired(value: object, now: datetime) -> bool:
    if value is None:
        return False
    if isinstance(value, datetime):
        return value < now
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return True
        # Convert aware datetime to naive UTC for comparison consistency.
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(tz=None).replace(tzinfo=None)
        return parsed < now
    return True
