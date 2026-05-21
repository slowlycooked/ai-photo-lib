from __future__ import annotations

from datetime import date, datetime, time as time_
from typing import Optional

from sqlalchemy.orm import Session

from ..models.photo import Photo


class PhotoRepository:
    """Write-side repository for Photo entities.

    Every query is explicitly scoped by ``project_id`` to enforce project
    isolation at the data-access layer.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── single-record reads ───────────────────────────────────────────────────

    def get_project_photo(
        self, project_id: int, photo_id: int
    ) -> Optional[Photo]:
        """Return a non-deleted photo that belongs to the given project."""
        return (
            self._db.query(Photo)
            .filter(
                Photo.id == photo_id,
                Photo.project_id == project_id,
                Photo.deleted_at.is_(None),
            )
            .first()
        )

    # ── list reads ────────────────────────────────────────────────────────────

    def list_project_photos(
        self,
        project_id: int,
        *,
        page: int = 1,
        page_size: int = 50,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> tuple[int, list[Photo]]:
        """Return (total, page_items) for photos in a project."""
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size

        q = self._db.query(Photo).filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
        if date_from is not None:
            q = q.filter(Photo.taken_at >= datetime.combine(date_from, time_.min))
        if date_to is not None:
            q = q.filter(Photo.taken_at < datetime.combine(date_to, time_.min))

        total = q.count()
        items = (
            q.order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return total, items

    # ── writes ────────────────────────────────────────────────────────────────

    def update_thumbnail(
        self, photo: Photo, thumbnail_path: str
    ) -> Photo:
        """Persist a new thumbnail path for a photo."""
        photo.thumbnail_path = thumbnail_path
        self._db.flush()
        return photo

    def mark_ai_indexed(self, photo: Photo) -> Photo:
        """Set photo status to 'indexed' after re-analysis is triggered."""
        photo.status = "indexed"
        self._db.flush()
        return photo
