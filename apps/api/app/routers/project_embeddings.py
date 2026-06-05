from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_manager
from ..database import get_db
from ..models.project import Project
from ..services.project_embeddings_app_service import ProjectEmbeddingsAppService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects-embeddings"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class EmbeddingStatusResponse(BaseModel):
    project_id: int
    total_analyzed_photos: int
    ready: int
    missing: int
    stale: int
    failed: int
    running_jobs: int
    queued_jobs: int
    embedding_model: str
    embedding_dimension: int
    input_version: str


class RebuildRequest(BaseModel):
    scope: str = "stale"   # all | stale | failed | missing | selected
    photo_ids: Optional[List[int]] = None
    force: bool = False


class RebuildResponse(BaseModel):
    created_jobs: int
    skipped_existing_jobs: int
    skipped_up_to_date: int
    total_checked: int
    message: str


# ── Status endpoint ───────────────────────────────────────────────────────────


@router.get("/{project_id}/embeddings/status", response_model=EmbeddingStatusResponse)
def get_embedding_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return embedding coverage statistics for a project."""
    service = ProjectEmbeddingsAppService(db)
    try:
        status = service.get_status(project_id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Embedding settings not configured for project {project_id}: {exc}",
        ) from exc

    return EmbeddingStatusResponse(
        project_id=status.project_id,
        total_analyzed_photos=status.total_analyzed_photos,
        ready=status.ready,
        missing=status.missing,
        stale=status.stale,
        failed=status.failed,
        running_jobs=status.running_jobs,
        queued_jobs=status.queued_jobs,
        embedding_model=status.embedding_model,
        embedding_dimension=status.embedding_dimension,
        input_version=status.input_version,
    )


# ── Rebuild endpoint ──────────────────────────────────────────────────────────


@router.post("/{project_id}/embeddings/rebuild", response_model=RebuildResponse)
def rebuild_project_embeddings(
    project_id: int,
    body: RebuildRequest = RebuildRequest(),
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Enqueue embedding rebuild jobs for analysed photos in a project.

    scope values:
      all      — enqueue every analysed photo
      stale    — only photos with stale/missing embeddings (default)
      failed   — only photos with failed embeddings
      missing  — only photos with no embedding row
      selected — only the photo_ids listed in the request body
    """
    scope = body.scope
    valid_scopes = {"all", "stale", "failed", "missing", "selected"}
    if scope not in valid_scopes:
        raise HTTPException(
            status_code=422,
            detail=f"scope must be one of {sorted(valid_scopes)}, got '{scope}'",
        )

    service = ProjectEmbeddingsAppService(db)
    try:
        result = service.rebuild(
            project_id=project_id,
            scope=scope,
            photo_ids=body.photo_ids,
            force=body.force,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Embedding settings not configured for project {project_id}: {exc}",
        ) from exc
    logger.info(
        "Embedding rebuild enqueued. project_id=%s scope=%s created=%s skipped_active=%s skipped_ok=%s",
        project_id,
        scope,
        result.created_jobs,
        result.skipped_existing_jobs,
        result.skipped_up_to_date,
    )
    return RebuildResponse(
        created_jobs=result.created_jobs,
        skipped_existing_jobs=result.skipped_existing_jobs,
        skipped_up_to_date=result.skipped_up_to_date,
        total_checked=result.total_checked,
        message=result.message,
    )


# ── Legacy endpoint (kept for backward compatibility) ─────────────────────────


@router.post("/{project_id}/ai/embeddings/rebuild", response_model=dict)
def rebuild_project_embeddings_legacy(
    project_id: int,
    response: Response,
    force: bool = False,
    only_failed: bool = False,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Legacy rebuild endpoint. Prefer POST /projects/{id}/embeddings/rebuild."""
    logger.warning(
        "Deprecated endpoint called: /projects/%s/ai/embeddings/rebuild. "
        "Use /projects/%s/embeddings/rebuild instead.",
        project_id,
        project_id,
    )
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 00:00:00 GMT"
    response.headers["Link"] = f'</projects/{project_id}/embeddings/rebuild>; rel="successor-version"'

    scope = "failed" if only_failed else "stale"
    req = RebuildRequest(scope=scope, force=force)
    result = rebuild_project_embeddings(project_id, req, project, db)
    return {
        "created_jobs": result.created_jobs,
        "skipped_existing_jobs": result.skipped_existing_jobs,
        "skipped_up_to_date": result.skipped_up_to_date,
        "total_checked": result.total_checked,
        "message": result.message,
    }
