from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_manager
from ..database import get_db
from ..models.project import Project
from ..schemas.ai import (
    AIJobListResponse,
    AIJobResponse,
    AIStatusResponse,
    RetryFailedResponse,
    StartAnalysisResponse,
)
from ..services.project_ai_jobs_app_service import ProjectAIJobsAppService

router = APIRouter(prefix="/projects", tags=["projects-ai-jobs"])


# ─── Enqueue ─────────────────────────────────────────────────────────────────


@router.post("/{project_id}/ai/analyze/start", response_model=StartAnalysisResponse)
def start_project_ai(
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Enqueue AI analysis jobs for all un-analysed photos in a project."""
    service = ProjectAIJobsAppService(db)
    return service.start_analysis(project.id)


# ─── Restart / re-analyse ─────────────────────────────────────────────────────


class ReanalyzeRequest(BaseModel):
    scope: Literal["all", "completed", "failed", "selected"] = "completed"
    photo_ids: List[int] = []
    clear_existing_analysis: bool = True


@router.post("/{project_id}/ai/analyze/restart", response_model=StartAnalysisResponse)
def restart_project_ai_analysis(
    project_id: int,
    body: ReanalyzeRequest,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Re-queue AI analysis for a subset of photos (by scope or explicit IDs)."""
    service = ProjectAIJobsAppService(db)
    return service.restart_analysis(
        project_id,
        scope=body.scope,
        photo_ids=body.photo_ids,
        clear_existing_analysis=body.clear_existing_analysis,
    )


# ─── Status ──────────────────────────────────────────────────────────────────


@router.get("/{project_id}/ai/status", response_model=AIStatusResponse)
def get_project_ai_status(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return per-status counts for AI jobs and embeddings in a project."""
    service = ProjectAIJobsAppService(db)
    return service.get_status(project.id)


# ─── Job list ────────────────────────────────────────────────────────────────


@router.get("/{project_id}/ai/jobs", response_model=AIJobListResponse)
def list_project_ai_jobs(
    project_id: int,
    status: Optional[str] = None,
    job_type: Optional[str] = Query(default=None),
    limit: int = 50,
    offset: int = 0,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """List AI jobs for a project with optional status filter and pagination."""
    service = ProjectAIJobsAppService(db)
    return service.list_jobs(
        project_id,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )


# ─── Retry / clear ───────────────────────────────────────────────────────────


@router.post("/{project_id}/ai/jobs/retry-failed", response_model=RetryFailedResponse)
def retry_project_failed_jobs(
    project_id: int,
    job_type: Optional[str] = Query(default=None),
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Re-queue all failed AI jobs that have not exceeded the retry limit."""
    service = ProjectAIJobsAppService(db)
    return service.retry_failed(project.id, job_type=job_type)


@router.delete("/{project_id}/ai/jobs/failed", response_model=dict)
def clear_project_failed_jobs(
    project_id: int,
    job_type: Optional[str] = Query(default=None),
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Delete all failed AI jobs for a project."""
    service = ProjectAIJobsAppService(db)
    return service.clear_failed(project.id, job_type=job_type)
