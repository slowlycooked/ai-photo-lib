from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.ai import AIJob, PhotoAIAnalysis


_MAX_ERROR_LEN = 12000


class AIJobRepository:
    """Write-side repository for AIJob entities.

    All job mutations happen here. Callers must commit or rollback via the
    session / UnitOfWork they control.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── enqueue ───────────────────────────────────────────────────────────────

    def enqueue_bulk(
        self,
        project_id: int,
        photo_ids: list[int],
        *,
        job_type: str = "analyze",
    ) -> list[AIJob]:
        """Create queued jobs for each photo_id and flush (no commit)."""
        jobs: list[AIJob] = []
        for photo_id in photo_ids:
            job = AIJob(
                project_id=project_id,
                photo_id=photo_id,
                job_type=job_type,
                status="queued",
                retry_count=0,
            )
            self._db.add(job)
            jobs.append(job)
        self._db.flush()
        return jobs

    def enqueue_bulk_unique(
        self,
        project_id: int,
        photo_ids: list[int],
        *,
        job_type: str = "analyze",
    ) -> tuple[list[AIJob], list[int]]:
        """Create queued jobs while skipping active queued/running duplicates."""
        deduped_photo_ids = list(dict.fromkeys(photo_ids))
        if not deduped_photo_ids:
            return [], []

        active_photo_id_rows = (
            self._db.query(AIJob.photo_id)
            .filter(
                AIJob.project_id == project_id,
                AIJob.job_type == job_type,
                AIJob.status.in_(["queued", "running"]),
                AIJob.photo_id.in_(deduped_photo_ids),
            )
            .distinct()
            .all()
        )
        active_photo_ids = {row[0] for row in active_photo_id_rows}

        created_jobs: list[AIJob] = []
        skipped_photo_ids: list[int] = []
        for photo_id in deduped_photo_ids:
            if photo_id in active_photo_ids:
                skipped_photo_ids.append(photo_id)
                continue
            job = AIJob(
                project_id=project_id,
                photo_id=photo_id,
                job_type=job_type,
                status="queued",
                retry_count=0,
            )
            self._db.add(job)
            created_jobs.append(job)
        self._db.flush()
        return created_jobs, skipped_photo_ids

    # ── claim ─────────────────────────────────────────────────────────────────

    def claim_next_queued(self) -> Optional[AIJob]:
        """Atomically claim the oldest queued job using SELECT FOR UPDATE SKIP LOCKED."""
        return (
            self._db.query(AIJob)
            .filter(AIJob.status == "queued")
            .order_by(AIJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )

    # ── status transitions ────────────────────────────────────────────────────

    def mark_running(self, job: AIJob) -> None:
        now = datetime.now(timezone.utc)
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        self._db.flush()

    def mark_success(self, job: AIJob) -> None:
        now = datetime.now(timezone.utc)
        job.status = "success"
        job.finished_at = now
        job.updated_at = now
        job.error_message = None
        job.parse_error = None
        self._db.flush()

    def mark_failed_or_retry(
        self,
        job: AIJob,
        error: str,
        *,
        retryable: bool,
        max_retries: int,
    ) -> str:
        """Update job to failed or requeue for retry. Returns final status."""
        now = datetime.now(timezone.utc)
        job.retry_count = (job.retry_count or 0) + 1
        job.error_message = error[:_MAX_ERROR_LEN]
        job.parse_error = error[:_MAX_ERROR_LEN]
        job.finished_at = now
        job.updated_at = now

        if retryable and job.retry_count < max_retries:
            job.status = "queued"
        else:
            job.status = "failed"

        self._db.flush()
        return job.status

    # ── bulk operations ───────────────────────────────────────────────────────

    def retry_failed_for_project(self, project_id: int, job_types: Optional[list[str]] = None) -> int:
        """Re-queue all failed jobs for a project. Returns count."""
        now = datetime.now(timezone.utc)
        rows = (
            self._db.query(AIJob)
            .filter(AIJob.project_id == project_id, AIJob.status == "failed")
        )
        if job_types:
            rows = rows.filter(AIJob.job_type.in_(job_types))
        rows = rows.all()
        for job in rows:
            job.status = "queued"
            job.retry_count = 0
            job.error_message = None
            job.parse_error = None
            job.updated_at = now
        self._db.flush()
        return len(rows)

    def delete_failed_for_project(self, project_id: int, job_types: Optional[list[str]] = None) -> int:
        """Hard-delete failed jobs for a project. Returns count."""
        query = self._db.query(AIJob).filter(
            AIJob.project_id == project_id,
            AIJob.status == "failed",
        )
        if job_types:
            query = query.filter(AIJob.job_type.in_(job_types))
        deleted = query.delete(synchronize_session=False)
        self._db.flush()
        return deleted

    def retry_failed_for_project_with_limit(
        self,
        project_id: int,
        max_retries: int,
        job_types: Optional[list[str]] = None,
    ) -> int:
        """Re-queue failed jobs under max_retries and keep retry_count history."""
        now = datetime.now(timezone.utc)
        rows = (
            self._db.query(AIJob)
            .filter(
                AIJob.project_id == project_id,
                AIJob.status == "failed",
                AIJob.retry_count < max_retries,
            )
        )
        if job_types:
            rows = rows.filter(AIJob.job_type.in_(job_types))
        rows = rows.all()
        for job in rows:
            job.status = "queued"
            job.error_message = None
            job.updated_at = now
        self._db.flush()
        return len(rows)

    def active_photo_ids_subquery(self, project_id: Optional[int] = None):
        q = select(AIJob.photo_id).where(AIJob.status.in_(["queued", "running"]))
        if project_id is not None:
            q = q.where(AIJob.project_id == project_id)
        return q

    def failed_photo_ids_subquery(self, project_id: int):
        return select(AIJob.photo_id).where(
            AIJob.project_id == project_id,
            AIJob.status == "failed",
        )

    def delete_by_project_photo_ids(
        self,
        project_id: int,
        photo_ids: list[int],
        *,
        statuses: Optional[list[str]] = None,
    ) -> int:
        q = self._db.query(AIJob).filter(
            AIJob.project_id == project_id,
            AIJob.photo_id.in_(photo_ids),
        )
        if statuses:
            q = q.filter(AIJob.status.in_(statuses))
        deleted = q.delete(synchronize_session=False)
        self._db.flush()
        return deleted

    # ── reads ─────────────────────────────────────────────────────────────────

    def count_by_status(self, project_id: int) -> dict[str, int]:
        """Return {status: count} for a project."""
        from sqlalchemy import func

        rows = (
            self._db.query(AIJob.status, func.count().label("n"))
            .filter(AIJob.project_id == project_id)
            .group_by(AIJob.status)
            .all()
        )
        return {row.status: row.n for row in rows}

    def list_for_project(
        self,
        project_id: int,
        *,
        status: Optional[str] = None,
        job_types: Optional[list[str]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[AIJob]]:
        """Return (total, items) for paginated job listing."""
        from sqlalchemy import func

        q = self._db.query(AIJob).filter(AIJob.project_id == project_id)
        if status:
            q = q.filter(AIJob.status == status)
        if job_types:
            q = q.filter(AIJob.job_type.in_(job_types))
        total = q.count()
        items = q.order_by(AIJob.created_at.desc()).offset(offset).limit(limit).all()
        return total, items

    # ── analysis read ─────────────────────────────────────────────────────────

    def get_analysis(self, project_id: int, photo_id: int) -> Optional[PhotoAIAnalysis]:
        return (
            self._db.query(PhotoAIAnalysis)
            .filter(
                PhotoAIAnalysis.project_id == project_id,
                PhotoAIAnalysis.photo_id == photo_id,
            )
            .first()
        )
