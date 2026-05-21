from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models.ai import PhotoAIAnalysis, PhotoEmbedding


class EmbeddingRepository:
    """Write-side repository for PhotoEmbedding entities.

    All methods are explicitly project-scoped.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_project_photo(
        self, project_id: int, photo_id: int
    ) -> Optional[PhotoEmbedding]:
        return (
            self._db.query(PhotoEmbedding)
            .filter(
                PhotoEmbedding.project_id == project_id,
                PhotoEmbedding.photo_id == photo_id,
            )
            .first()
        )

    def count_by_status(self, project_id: int) -> dict[str, int]:
        from sqlalchemy import func

        rows = (
            self._db.query(PhotoEmbedding.embedding_status, func.count().label("n"))
            .filter(PhotoEmbedding.project_id == project_id)
            .group_by(PhotoEmbedding.embedding_status)
            .all()
        )
        return {row.embedding_status: row.n for row in rows}

    def list_stale_for_project(
        self,
        project_id: int,
        *,
        statuses: Optional[list[str]] = None,
        limit: int = 1000,
    ) -> list[tuple[PhotoEmbedding, PhotoAIAnalysis]]:
        """Return (embedding, analysis) pairs that need rebuilding."""
        if statuses is None:
            statuses = ["stale", "failed"]

        return (
            self._db.query(PhotoEmbedding, PhotoAIAnalysis)
            .join(
                PhotoAIAnalysis,
                (PhotoAIAnalysis.project_id == PhotoEmbedding.project_id)
                & (PhotoAIAnalysis.photo_id == PhotoEmbedding.photo_id),
            )
            .filter(
                PhotoEmbedding.project_id == project_id,
                PhotoEmbedding.embedding_status.in_(statuses),
            )
            .limit(limit)
            .all()
        )
