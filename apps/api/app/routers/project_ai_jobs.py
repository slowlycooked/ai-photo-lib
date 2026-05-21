from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..config import settings
from ..database import get_db
from ..models.ai import AIJob, PhotoAIAnalysis, PhotoEmbedding
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.ai import (
    AIJobListResponse,
    AIJobResponse,
    AIStatusResponse,
    RetryFailedResponse,
    StartAnalysisResponse,
)

router = APIRouter(prefix="/projects", tags=["projects-ai-jobs"])


# ─── Enqueue ─────────────────────────────────────────────────────────────────


@router.post("/{project_id}/ai/analyze/start", response_model=StartAnalysisResponse)
def start_project_ai(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Enqueue AI analysis jobs for all un-analysed photos in a project."""
    project_id = project.id

    active_photo_ids = (
        db.query(AIJob.photo_id)
        .filter(AIJob.status.in_(["queued", "running"]))
        .subquery()
    )
    analyzed_photo_ids = db.query(PhotoAIAnalysis.photo_id).subquery()

    photos_to_process = (
        db.query(Photo)
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.id.not_in(active_photo_ids),
            Photo.id.not_in(analyzed_photo_ids),
        )
        .all()
    )

    count = 0
    for photo in photos_to_process:
        db.add(
            AIJob(
                photo_id=photo.id,
                project_id=project_id,
                job_type="analyze",
                status="queued",
            )
        )
        count += 1

    db.commit()
    return StartAnalysisResponse(created_jobs=count, message="AI analysis jobs created")


# ─── Restart / re-analyse ─────────────────────────────────────────────────────


class ReanalyzeRequest(BaseModel):
    scope: Literal["all", "completed", "failed", "selected"] = "completed"
    photo_ids: List[int] = []
    clear_existing_analysis: bool = True


@router.post("/{project_id}/ai/analyze/restart", response_model=StartAnalysisResponse)
def restart_project_ai_analysis(
    project_id: int,
    body: ReanalyzeRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Re-queue AI analysis for a subset of photos (by scope or explicit IDs)."""
    active_photo_ids = (
        db.query(AIJob.photo_id)
        .filter(
            AIJob.project_id == project_id,
            AIJob.status.in_(["queued", "running"]),
        )
        .subquery()
    )

    query = db.query(Photo).filter(
        Photo.project_id == project_id,
        Photo.deleted_at.is_(None),
        Photo.id.not_in(active_photo_ids),
    )

    if body.scope == "completed":
        query = query.join(
            PhotoAIAnalysis,
            (PhotoAIAnalysis.photo_id == Photo.id)
            & (PhotoAIAnalysis.project_id == project_id),
        )
    elif body.scope == "selected":
        if not body.photo_ids:
            return StartAnalysisResponse(created_jobs=0, message="No selected photos")
        query = query.filter(Photo.id.in_(body.photo_ids))
    elif body.scope == "failed":
        failed_photo_ids = (
            db.query(AIJob.photo_id)
            .filter(
                AIJob.project_id == project_id,
                AIJob.status == "failed",
            )
            .subquery()
        )
        query = query.filter(Photo.id.in_(failed_photo_ids))
    # scope == "all": no extra filter needed

    photos = query.all()
    photo_ids = [p.id for p in photos]

    if body.clear_existing_analysis and photo_ids:
        db.query(PhotoAIAnalysis).filter(
            PhotoAIAnalysis.project_id == project_id,
            PhotoAIAnalysis.photo_id.in_(photo_ids),
        ).delete(synchronize_session=False)

    if photo_ids:
        db.query(AIJob).filter(
            AIJob.project_id == project_id,
            AIJob.photo_id.in_(photo_ids),
            AIJob.status.in_(["success", "failed"]),
        ).delete(synchronize_session=False)

    count = 0
    for photo in photos:
        db.add(
            AIJob(
                photo_id=photo.id,
                project_id=project_id,
                job_type="reanalyze",
                status="queued",
            )
        )
        photo.status = "indexed"
        count += 1

    db.commit()
    return StartAnalysisResponse(created_jobs=count, message="AI re-analysis jobs created")


# ─── Status ──────────────────────────────────────────────────────────────────


@router.get("/{project_id}/ai/status", response_model=AIStatusResponse)
def get_project_ai_status(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return per-status counts for AI jobs and embeddings in a project."""
    project_id = project.id

    rows = (
        db.query(AIJob.status, func.count(AIJob.id))
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id)
        .group_by(AIJob.status)
        .all()
    )
    counts: dict[str, int] = {status: cnt for status, cnt in rows}
    total = sum(counts.values())

    analyzed_count = (
        db.query(func.count(PhotoAIAnalysis.id))
        .filter(PhotoAIAnalysis.project_id == project_id)
        .scalar()
        or 0
    )
    embedding_ready_count, embedding_failed_count, embedding_stale_count = (
        _get_project_embedding_counts(db, project_id)
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


# ─── Job list ────────────────────────────────────────────────────────────────


@router.get("/{project_id}/ai/jobs", response_model=AIJobListResponse)
def list_project_ai_jobs(
    project_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """List AI jobs for a project with optional status filter and pagination."""
    limit = max(1, min(limit, 200))
    query = (
        db.query(AIJob, Photo.file_name)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id)
    )
    if status:
        query = query.filter(AIJob.status == status)

    total = query.count()
    rows = query.order_by(AIJob.created_at.desc()).offset(offset).limit(limit).all()

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
            file_name=file_name,
        )
        for job, file_name in rows
    ]
    return AIJobListResponse(total=total, items=items)


# ─── Retry / clear ───────────────────────────────────────────────────────────


@router.post("/{project_id}/ai/jobs/retry-failed", response_model=RetryFailedResponse)
def retry_project_failed_jobs(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Re-queue all failed AI jobs that have not exceeded the retry limit."""
    from datetime import timezone

    project_id = project.id
    jobs = (
        db.query(AIJob)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(
            Photo.project_id == project_id,
            AIJob.status == "failed",
            AIJob.retry_count < settings.ai_max_retries,
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    count = 0
    for job in jobs:
        job.status = "queued"
        job.error_message = None
        job.updated_at = now
        count += 1
    db.commit()
    return RetryFailedResponse(retried_jobs=count, message="Failed jobs re-queued")


@router.delete("/{project_id}/ai/jobs/failed", response_model=dict)
def clear_project_failed_jobs(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Delete all failed AI jobs for a project."""
    project_id = project.id
    failed = (
        db.query(AIJob)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id, AIJob.status == "failed")
    )
    count = failed.count()
    ids = [job.id for job in failed.all()]
    if ids:
        db.query(AIJob).filter(AIJob.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted_jobs": count, "message": "Failed jobs cleared"}


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _get_project_embedding_counts(
    db: Session, project_id: int
) -> tuple[int, int, int]:
    """Return (ready, failed, stale) with compatibility for legacy schemas."""
    embedding_columns = _get_photo_embeddings_columns(db)
    if not embedding_columns:
        return 0, 0, 0

    has_project_id = "project_id" in embedding_columns
    has_embedding_status = "embedding_status" in embedding_columns

    if has_embedding_status:
        if has_project_id:
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
        else:
            ready_count = (
                db.query(func.count())
                .select_from(PhotoEmbedding)
                .join(Photo, PhotoEmbedding.photo_id == Photo.id)
                .filter(
                    Photo.project_id == project_id,
                    PhotoEmbedding.embedding_status == "ready",
                )
                .scalar()
                or 0
            )
            failed_count = (
                db.query(func.count())
                .select_from(PhotoEmbedding)
                .join(Photo, PhotoEmbedding.photo_id == Photo.id)
                .filter(
                    Photo.project_id == project_id,
                    PhotoEmbedding.embedding_status == "failed",
                )
                .scalar()
                or 0
            )
            stale_count = (
                db.query(func.count())
                .select_from(PhotoEmbedding)
                .join(Photo, PhotoEmbedding.photo_id == Photo.id)
                .filter(
                    Photo.project_id == project_id,
                    PhotoEmbedding.embedding_status == "stale",
                )
                .scalar()
                or 0
            )
        return ready_count, failed_count, stale_count

    # Legacy schema: no status column → treat all rows as ready
    if has_project_id:
        ready_count = (
            db.query(func.count())
            .select_from(PhotoEmbedding)
            .filter(PhotoEmbedding.project_id == project_id)
            .scalar()
            or 0
        )
    else:
        ready_count = (
            db.query(func.count())
            .select_from(PhotoEmbedding)
            .join(Photo, PhotoEmbedding.photo_id == Photo.id)
            .filter(Photo.project_id == project_id)
            .scalar()
            or 0
        )
    return ready_count, 0, 0


def _get_photo_embeddings_columns(db: Session) -> set[str]:
    try:
        return {
            column["name"]
            for column in inspect(db.get_bind()).get_columns("photo_embeddings")
        }
    except Exception:  # noqa: BLE001
        return set()
