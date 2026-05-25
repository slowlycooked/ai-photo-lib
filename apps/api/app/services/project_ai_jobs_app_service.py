from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import PhotoAIAnalysis, PhotoEmbedding
from ..repositories.unit_of_work import UnitOfWork
from ..schemas.ai import (
    AIJobListResponse,
    AIJobResponse,
    AIStatusResponse,
    RetryFailedResponse,
    StartAnalysisResponse,
)


class ProjectAIJobsAppService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._uow = UnitOfWork(db)

    def start_analysis(self, project_id: int) -> StartAnalysisResponse:
        active_photo_ids = self._uow.ai_jobs.active_photo_ids_subquery()
        analyzed_photo_ids = self._uow.photos.analyzed_photo_ids_subquery()

        photos_to_process = self._uow.photos.list_analysis_candidates(
            project_id,
            active_photo_ids_subquery=active_photo_ids,
            analyzed_photo_ids_subquery=analyzed_photo_ids,
        )

        photo_ids = [photo.id for photo in photos_to_process]
        created_jobs, _ = self._uow.ai_jobs.enqueue_bulk_unique(
            project_id,
            photo_ids,
            job_type="analyze",
        )

        self._uow.commit()
        return StartAnalysisResponse(
            created_jobs=len(created_jobs),
            message="AI analysis jobs created",
        )

    def restart_analysis(
        self,
        project_id: int,
        *,
        scope: str,
        photo_ids: list[int],
        clear_existing_analysis: bool,
    ) -> StartAnalysisResponse:
        if scope == "selected" and not photo_ids:
            return StartAnalysisResponse(created_jobs=0, message="No selected photos")

        active_photo_ids = self._uow.ai_jobs.active_photo_ids_subquery(project_id)
        failed_photo_ids = self._uow.ai_jobs.failed_photo_ids_subquery(project_id)

        photos = self._uow.photos.list_reanalysis_candidates(
            project_id,
            scope=scope,
            selected_photo_ids=photo_ids,
            active_photo_ids_subquery=active_photo_ids,
            failed_photo_ids_subquery=failed_photo_ids,
        )
        selected_photo_ids = [p.id for p in photos]

        if clear_existing_analysis and selected_photo_ids:
            self._db.query(PhotoAIAnalysis).filter(
                PhotoAIAnalysis.project_id == project_id,
                PhotoAIAnalysis.photo_id.in_(selected_photo_ids),
            ).delete(synchronize_session=False)

        if selected_photo_ids:
            self._uow.ai_jobs.delete_by_project_photo_ids(
                project_id,
                selected_photo_ids,
                statuses=["success", "failed"],
            )

        for photo in photos:
            photo.status = "indexed"

        created_jobs, _ = self._uow.ai_jobs.enqueue_bulk_unique(
            project_id,
            selected_photo_ids,
            job_type="reanalyze",
        )

        self._uow.commit()
        return StartAnalysisResponse(
            created_jobs=len(created_jobs),
            message="AI re-analysis jobs created",
        )

    def get_status(self, project_id: int) -> AIStatusResponse:
        counts = self._uow.ai_jobs.count_by_status(project_id)
        total = sum(counts.values())

        analyzed_count = self._uow.photos.count_analyzed(project_id)
        embedding_ready_count, embedding_failed_count, embedding_stale_count = (
            _get_project_embedding_counts(self._db, project_id)
        )
        embedding_missing_count = max(
            0,
            analyzed_count
            - (embedding_ready_count + embedding_failed_count + embedding_stale_count),
        )

        return AIStatusResponse(
            queued=counts.get("queued", 0),
            running=counts.get("running", 0),
            success=counts.get("success", 0),
            failed=counts.get("failed", 0),
            total=total,
            analyzed_count=analyzed_count,
            embedding_ready_count=embedding_ready_count,
            embedding_missing_count=embedding_missing_count,
            embedding_failed_count=embedding_failed_count,
            embedding_stale_count=embedding_stale_count,
        )

    def list_jobs(
        self,
        project_id: int,
        *,
        status: Optional[str],
        job_type: Optional[str],
        limit: int,
        offset: int,
    ) -> AIJobListResponse:
        limit = max(1, min(limit, 200))
        job_types = _parse_job_types(job_type)
        total, jobs = self._uow.ai_jobs.list_for_project(
            project_id,
            status=status,
            job_types=job_types,
            limit=limit,
            offset=offset,
        )
        file_name_map = self._uow.photos.list_file_names_by_ids(
            project_id,
            [job.photo_id for job in jobs],
        )

        items = [
            AIJobResponse(
                id=job.id,
                photo_id=job.photo_id,
                job_type=job.job_type,
                status=job.status,
                retry_count=job.retry_count,
                error_message=job.error_message,
                prompt_template_id=job.prompt_template_id,
                prompt_version=job.prompt_version,
                model_name=job.model_name,
                model_params=job.model_params,
                raw_model_output=job.raw_model_output,
                parse_error=job.parse_error,
                started_at=job.started_at,
                finished_at=job.finished_at,
                created_at=job.created_at,
                updated_at=job.updated_at,
                file_name=file_name_map.get(job.photo_id),
            )
            for job in jobs
        ]
        return AIJobListResponse(total=total, items=items)

    def retry_failed(self, project_id: int, *, job_type: Optional[str]) -> RetryFailedResponse:
        job_types = _parse_job_types(job_type)
        count = self._uow.ai_jobs.retry_failed_for_project_with_limit(
            project_id,
            settings.ai_max_retries,
            job_types=job_types,
        )

        self._uow.commit()
        return RetryFailedResponse(retried_jobs=count, message="Failed jobs re-queued")

    def clear_failed(self, project_id: int, *, job_type: Optional[str]) -> dict:
        job_types = _parse_job_types(job_type)
        count = self._uow.ai_jobs.delete_failed_for_project(project_id, job_types=job_types)

        self._uow.commit()
        return {"deleted_jobs": count, "message": "Failed jobs cleared"}


def _get_project_embedding_counts(
    db: Session, project_id: int
) -> tuple[int, int, int]:
    ready_count = (
        db.query(func.count())
        .select_from(PhotoEmbedding)
        .filter(
            PhotoEmbedding.project_id == project_id,
            PhotoEmbedding.embedding_status == "ready",
        )
        .scalar()
        or 0
    )
    failed_count = (
        db.query(func.count())
        .select_from(PhotoEmbedding)
        .filter(
            PhotoEmbedding.project_id == project_id,
            PhotoEmbedding.embedding_status == "failed",
        )
        .scalar()
        or 0
    )
    stale_count = (
        db.query(func.count())
        .select_from(PhotoEmbedding)
        .filter(
            PhotoEmbedding.project_id == project_id,
            PhotoEmbedding.embedding_status == "stale",
        )
        .scalar()
        or 0
    )
    return ready_count, failed_count, stale_count


def _parse_job_types(job_type: Optional[str]) -> Optional[list[str]]:
    if not job_type:
        return None
    parts = [item.strip() for item in job_type.split(",") if item.strip()]
    return parts or None
