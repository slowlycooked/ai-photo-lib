from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..models.ai import AIJob, PhotoAIAnalysis, PhotoEmbedding
from ..models.photo import Photo
from .embedding_service import EMBEDDING_INPUT_VERSION, is_embedding_stale
from .project_embedding_settings_service import resolve_embedding_settings_strict


@dataclass(frozen=True)
class EmbeddingStatusSummary:
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
    input_version: str = EMBEDDING_INPUT_VERSION


@dataclass(frozen=True)
class EmbeddingRebuildSummary:
    created_jobs: int
    skipped_existing_jobs: int
    skipped_up_to_date: int
    total_checked: int
    message: str


@dataclass
class ProjectEmbeddingsAppService:
    db: Session

    def get_status(self, project_id: int) -> EmbeddingStatusSummary:
        embed_cfg = resolve_embedding_settings_strict(self.db, project_id)
        resolved_model = embed_cfg["model_name"]
        resolved_dim = embed_cfg["embedding_dimension"]
        resolved_document_prefix = embed_cfg.get("input_prefix_document")

        rows = (
            self.db.query(PhotoAIAnalysis, PhotoEmbedding, Photo)
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
            self.db.query(func.count())
            .filter(
                AIJob.project_id == project_id,
                AIJob.job_type == "embed",
                AIJob.status == "running",
            )
            .scalar()
            or 0
        )
        queued_jobs = (
            self.db.query(func.count())
            .filter(
                AIJob.project_id == project_id,
                AIJob.job_type == "embed",
                AIJob.status == "queued",
            )
            .scalar()
            or 0
        )

        return EmbeddingStatusSummary(
            project_id=project_id,
            total_analyzed_photos=len(rows),
            ready=ready,
            missing=missing,
            stale=stale,
            failed=failed,
            running_jobs=running_jobs,
            queued_jobs=queued_jobs,
            embedding_model=resolved_model,
            embedding_dimension=resolved_dim,
        )

    def rebuild(
        self,
        *,
        project_id: int,
        scope: str,
        photo_ids: Optional[list[int]],
        force: bool,
    ) -> EmbeddingRebuildSummary:
        embed_cfg = resolve_embedding_settings_strict(self.db, project_id)
        resolved_model = embed_cfg["model_name"]
        resolved_dim = embed_cfg["embedding_dimension"]
        resolved_document_prefix = embed_cfg.get("input_prefix_document")

        active_embed_photo_ids = self._get_active_embed_photo_ids(project_id)

        base_query = (
            self.db.query(PhotoAIAnalysis, PhotoEmbedding, Photo)
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

        if scope == "selected" and photo_ids:
            base_query = base_query.filter(PhotoAIAnalysis.photo_id.in_(photo_ids))

        rows = base_query.all()

        created_jobs = 0
        skipped_existing_jobs = 0
        skipped_up_to_date = 0

        for analysis, embedding, photo in rows:
            photo_id = analysis.photo_id
            if photo_id in active_embed_photo_ids:
                skipped_existing_jobs += 1
                continue

            if force or scope == "all":
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
                should_enqueue = embedding is not None and embedding.embedding_status == "failed"
            elif scope == "missing":
                should_enqueue = embedding is None
            elif scope == "selected":
                should_enqueue = True
            else:
                should_enqueue = False

            if not should_enqueue:
                skipped_up_to_date += 1
                continue

            self.db.add(
                AIJob(
                    project_id=project_id,
                    photo_id=photo_id,
                    job_type="embed",
                    status="queued",
                )
            )
            created_jobs += 1

        self.db.commit()
        return EmbeddingRebuildSummary(
            created_jobs=created_jobs,
            skipped_existing_jobs=skipped_existing_jobs,
            skipped_up_to_date=skipped_up_to_date,
            total_checked=len(rows),
            message="Embedding rebuild jobs processed",
        )

    def _get_active_embed_photo_ids(self, project_id: int) -> set[int]:
        return {
            photo_id
            for (photo_id,) in (
                self.db.query(AIJob.photo_id)
                .filter(
                    AIJob.project_id == project_id,
                    AIJob.job_type == "embed",
                    AIJob.status.in_(["queued", "running"]),
                )
                .all()
            )
        }