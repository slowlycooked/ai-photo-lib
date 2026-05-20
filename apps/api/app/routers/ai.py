from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.ai import AIJob, PhotoAIAnalysis
from ..models.photo import Photo
from ..schemas.ai import (
    AIJobListResponse,
    AIJobResponse,
    AIStatusResponse,
    RetryFailedResponse,
    StartAnalysisResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DEPRECATED: All endpoints in this router are superseded by the project-scoped
# equivalents under /projects/{project_id}/ai/...  These routes will be removed
# in a future release.  Do NOT add new features here.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/ai", tags=["ai [deprecated]"])

_DEPRECATION_MSG = (
    "Global /ai/* endpoints are deprecated. "
    "Use /projects/{project_id}/ai/* instead."
)


@router.post("/analyze/start", response_model=StartAnalysisResponse,
             deprecated=True)
def start_analysis(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """[DEPRECATED] Use POST /projects/{project_id}/ai/analyze/start instead."""
    logger.warning(_DEPRECATION_MSG)
    # Sub-query: photo_ids that already have a queued or running job
    active_photo_ids = (
        db.query(AIJob.photo_id)
        .filter(AIJob.status.in_(["queued", "running"]))
        .subquery()
    )
    # Sub-query: photo_ids that already have a successful analysis
    analyzed_photo_ids = (
        db.query(PhotoAIAnalysis.photo_id).subquery()
    )

    photos_query = db.query(Photo).filter(
        Photo.deleted_at.is_(None),
        Photo.id.not_in(active_photo_ids),
        Photo.id.not_in(analyzed_photo_ids),
    )
    if project_id is not None:
        photos_query = photos_query.filter(Photo.project_id == project_id)

    photos_to_process = photos_query.all()

    count = 0
    for photo in photos_to_process:
        job = AIJob(
            photo_id=photo.id,
            project_id=photo.project_id,
            job_type="analyze",
            status="queued",
        )
        db.add(job)
        count += 1

    db.commit()
    return StartAnalysisResponse(created_jobs=count, message="AI analysis jobs created")


@router.get("/status", response_model=AIStatusResponse, deprecated=True)
def get_ai_status(db: Session = Depends(get_db)):
    """[DEPRECATED] Use GET /projects/{project_id}/ai/status instead."""
    logger.warning(_DEPRECATION_MSG)
    rows = (
        db.query(AIJob.status, func.count(AIJob.id))
        .group_by(AIJob.status)
        .all()
    )
    counts: dict[str, int] = {status: cnt for status, cnt in rows}
    total = sum(counts.values())
    return AIStatusResponse(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        total=total,
    )


@router.get("/jobs", response_model=AIJobListResponse, deprecated=True)
def list_ai_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """[DEPRECATED] Use GET /projects/{project_id}/ai/jobs instead."""
    logger.warning(_DEPRECATION_MSG)
    limit = max(1, min(limit, 200))
    query = db.query(AIJob, Photo.file_name).join(
        Photo, AIJob.photo_id == Photo.id
    )
    if status:
        query = query.filter(AIJob.status == status)

    total = query.count()
    rows = query.order_by(AIJob.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for job, file_name in rows:
        item = AIJobResponse(
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
        items.append(item)

    return AIJobListResponse(total=total, items=items)


@router.post("/jobs/retry-failed", response_model=RetryFailedResponse, deprecated=True)
def retry_failed_jobs(db: Session = Depends(get_db)):
    """[DEPRECATED] Use POST /projects/{project_id}/ai/jobs/retry-failed instead."""
    logger.warning(_DEPRECATION_MSG)
    jobs = (
        db.query(AIJob)
        .filter(
            AIJob.status == "failed",
            AIJob.retry_count < settings.ai_max_retries,
        )
        .all()
    )
    count = 0
    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = "queued"
        job.error_message = None
        job.updated_at = now
        count += 1

    db.commit()
    return RetryFailedResponse(retried_jobs=count, message="Failed jobs re-queued")


@router.delete("/jobs/clear-failed", response_model=dict, deprecated=True)
def clear_failed_jobs(db: Session = Depends(get_db)):
    """[DEPRECATED] Use DELETE /projects/{project_id}/ai/jobs/failed instead."""
    logger.warning(_DEPRECATION_MSG)
    failed_jobs = db.query(AIJob).filter(AIJob.status == "failed")
    count = failed_jobs.count()
    failed_jobs.delete(synchronize_session=False)
    db.commit()
    return {"deleted_jobs": count, "message": "Failed jobs cleared successfully"}
