from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.ai import AIJob, PhotoAIAnalysis, PhotoEmbedding
from ..models.photo import Photo
from ..models.project import Project
from ..services.embedding_service import EMBEDDING_INPUT_VERSION, is_embedding_stale
from ..services.project_embedding_settings_service import resolve_embedding_settings_strict

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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_active_embed_photo_ids(db: Session, project_id: int) -> set[int]:
    return {
        photo_id
        for (photo_id,) in (
            db.query(AIJob.photo_id)
            .filter(
                AIJob.project_id == project_id,
                AIJob.job_type == "embed",
                AIJob.status.in_(["queued", "running"]),
            )
            .all()
        )
    }


# ── Status endpoint ───────────────────────────────────────────────────────────


@router.get("/{project_id}/embeddings/status", response_model=EmbeddingStatusResponse)
def get_embedding_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return embedding coverage statistics for a project."""
    try:
        embed_cfg = resolve_embedding_settings_strict(db, project_id)
        resolved_model = embed_cfg["model_name"]
        resolved_dim = embed_cfg["embedding_dimension"]
        resolved_document_prefix = embed_cfg.get("input_prefix_document")
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Embedding settings not configured for project {project_id}: {exc}",
        ) from exc

    rows = (
        db.query(PhotoAIAnalysis, PhotoEmbedding, Photo)
        .join(
            Photo,
            and_(
                Photo.project_id == PhotoAIAnalysis.project_id,
                Photo.id == PhotoAIAnalysis.photo_id,
            ),
        )
        .outerjoin(
            PhotoEmbedding,
            and_(
                PhotoEmbedding.project_id == PhotoAIAnalysis.project_id,
                PhotoEmbedding.photo_id == PhotoAIAnalysis.photo_id,
            ),
        )
        .filter(PhotoAIAnalysis.project_id == project_id)
        .all()
    )

    total_analyzed = len(rows)
    ready = 0
    missing = 0
    stale = 0
    failed = 0

    for analysis, embedding, photo in rows:
        if embedding is None:
            missing += 1
        elif embedding.embedding_status == "failed":
            failed += 1
        elif is_embedding_stale(
            analysis,
            embedding,
            model_name=resolved_model,
            dimension=resolved_dim,
            photo=photo,
            input_prefix_document=resolved_document_prefix,
        ):
            stale += 1
        else:
            ready += 1

    running_jobs = (
        db.query(func.count())
        .filter(
            AIJob.project_id == project_id,
            AIJob.job_type == "embed",
            AIJob.status == "running",
        )
        .scalar()
        or 0
    )
    queued_jobs = (
        db.query(func.count())
        .filter(
            AIJob.project_id == project_id,
            AIJob.job_type == "embed",
            AIJob.status == "queued",
        )
        .scalar()
        or 0
    )

    return EmbeddingStatusResponse(
        project_id=project_id,
        total_analyzed_photos=total_analyzed,
        ready=ready,
        missing=missing,
        stale=stale,
        failed=failed,
        running_jobs=running_jobs,
        queued_jobs=queued_jobs,
        embedding_model=resolved_model,
        embedding_dimension=resolved_dim,
        input_version=EMBEDDING_INPUT_VERSION,
    )


# ── Rebuild endpoint ──────────────────────────────────────────────────────────


@router.post("/{project_id}/embeddings/rebuild", response_model=RebuildResponse)
def rebuild_project_embeddings(
    project_id: int,
    body: RebuildRequest = RebuildRequest(),
    project: Project = Depends(require_project),
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

    try:
        embed_cfg = resolve_embedding_settings_strict(db, project_id)
        resolved_model = embed_cfg["model_name"]
        resolved_dim = embed_cfg["embedding_dimension"]
        resolved_document_prefix = embed_cfg.get("input_prefix_document")
    except RuntimeError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Embedding settings not configured for project {project_id}: {exc}",
        ) from exc

    active_embed_photo_ids = _get_active_embed_photo_ids(db, project_id)

    base_query = (
        db.query(PhotoAIAnalysis, PhotoEmbedding, Photo)
        .join(
            Photo,
            and_(
                Photo.project_id == PhotoAIAnalysis.project_id,
                Photo.id == PhotoAIAnalysis.photo_id,
            ),
        )
        .outerjoin(
            PhotoEmbedding,
            and_(
                PhotoEmbedding.project_id == PhotoAIAnalysis.project_id,
                PhotoEmbedding.photo_id == PhotoAIAnalysis.photo_id,
            ),
        )
        .filter(PhotoAIAnalysis.project_id == project_id)
    )

    if scope == "selected":
        if not body.photo_ids:
            raise HTTPException(
                status_code=422,
                detail="photo_ids must be provided when scope='selected'",
            )
        base_query = base_query.filter(PhotoAIAnalysis.photo_id.in_(body.photo_ids))

    rows = base_query.all()

    created_jobs = 0
    skipped_existing_jobs = 0
    skipped_up_to_date = 0
    total_checked = len(rows)

    for analysis, embedding, photo in rows:
        photo_id = analysis.photo_id

        if photo_id in active_embed_photo_ids:
            skipped_existing_jobs += 1
            continue

        if body.force or scope == "all":
            should_enqueue = True
        elif scope == "stale":
            should_enqueue = is_embedding_stale(
                analysis,
                embedding,
                model_name=resolved_model,
                dimension=resolved_dim,
                photo=photo,
                input_prefix_document=resolved_document_prefix,
            )
        elif scope == "failed":
            should_enqueue = (
                embedding is not None and embedding.embedding_status == "failed"
            )
        elif scope == "missing":
            should_enqueue = embedding is None
        elif scope == "selected":
            should_enqueue = True
        else:
            should_enqueue = False

        if not should_enqueue:
            skipped_up_to_date += 1
            continue

        db.add(
            AIJob(
                project_id=project_id,
                photo_id=photo_id,
                job_type="embed",
                status="queued",
            )
        )
        created_jobs += 1

    db.commit()
    logger.info(
        "Embedding rebuild enqueued. project_id=%s scope=%s created=%s skipped_active=%s skipped_ok=%s",
        project_id,
        scope,
        created_jobs,
        skipped_existing_jobs,
        skipped_up_to_date,
    )
    return RebuildResponse(
        created_jobs=created_jobs,
        skipped_existing_jobs=skipped_existing_jobs,
        skipped_up_to_date=skipped_up_to_date,
        total_checked=total_checked,
        message="Embedding rebuild jobs processed",
    )


# ── Legacy endpoint (kept for backward compatibility) ─────────────────────────


@router.post("/{project_id}/ai/embeddings/rebuild", response_model=dict)
def rebuild_project_embeddings_legacy(
    project_id: int,
    response: Response,
    force: bool = False,
    only_failed: bool = False,
    project: Project = Depends(require_project),
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
