from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..config import settings
from ..database import get_db
from ..models.ai import AIJob, PhotoAIAnalysis, PhotoEmbedding
from ..models.photo import Photo
from ..models.project import Project
from ..services.embedding_service import is_embedding_stale
from ..services.project_ai_service import get_or_create_project_ai_settings

router = APIRouter(prefix="/projects", tags=["projects-embeddings"])


@router.post("/{project_id}/ai/embeddings/rebuild", response_model=dict)
def rebuild_project_embeddings(
    project_id: int,
    force: bool = False,
    only_failed: bool = False,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Enqueue embedding rebuild jobs for analysed photos in a project."""
    ai_settings = get_or_create_project_ai_settings(db, project_id)
    active_embed_photo_ids = {
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

    rows = (
        db.query(PhotoAIAnalysis, PhotoEmbedding)
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

    created_jobs = 0
    skipped_existing_jobs = 0
    skipped_up_to_date = 0
    total_checked = len(rows)

    resolved_model = (
        settings.embedding_model
        or ai_settings.model_name
        or settings.openai_model
    )

    for analysis, embedding in rows:
        photo_id = analysis.photo_id
        if photo_id in active_embed_photo_ids:
            skipped_existing_jobs += 1
            continue

        if force:
            should_enqueue = True
        elif only_failed:
            should_enqueue = embedding is not None and embedding.embedding_status == "failed"
        else:
            should_enqueue = is_embedding_stale(
                analysis,
                embedding,
                model_name=resolved_model,
                dimension=settings.embedding_dimension,
            )

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
    return {
        "created_jobs": created_jobs,
        "skipped_existing_jobs": skipped_existing_jobs,
        "skipped_up_to_date": skipped_up_to_date,
        "total_checked": total_checked,
        "message": "Embedding rebuild jobs processed",
    }
