from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as time_
from typing import Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from .folder_service import apply_folder_filter


@dataclass
class ProjectPhotosQueryService:
    db: Session

    def list_photos(
        self,
        *,
        project_id: int,
        page: int,
        page_size: int,
        date_from: Optional[date],
        date_to: Optional[date],
        folder_id: Optional[int],
        folder_scope: str,
    ) -> tuple[int, list[Photo]]:
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        base_query = self.db.query(Photo).filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.status != "quarantined",
        )
        if date_from is not None:
            base_query = base_query.filter(
                Photo.taken_at >= datetime.combine(date_from, time_.min)
            )
        if date_to is not None:
            base_query = base_query.filter(
                Photo.taken_at < datetime.combine(date_to, time_.min)
            )
        if folder_id is not None:
            base_query = apply_folder_filter(
                base_query,
                self.db,
                project_id,
                folder_id,
                folder_scope,
            )

        total = base_query.count()
        photos = (
            base_query.order_by(
                Photo.taken_at.desc().nullslast(),
                Photo.created_at.desc(),
                Photo.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return total, photos

    def timeline(
        self,
        *,
        project_id: int,
        folder_id: Optional[int],
        folder_scope: str,
    ) -> list[dict[str, int | str]]:
        base_query = self.db.query(Photo).filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.status != "quarantined",
            Photo.taken_at.is_not(None),
        )
        if folder_id is not None:
            base_query = apply_folder_filter(
                base_query,
                self.db,
                project_id,
                folder_id,
                folder_scope,
            )

        rows = (
            base_query.with_entities(
                extract("year", Photo.taken_at).label("year"),
                extract("month", Photo.taken_at).label("month"),
                func.count(Photo.id).label("count"),
            )
            .group_by("year", "month")
            .order_by(
                extract("year", Photo.taken_at).desc(),
                extract("month", Photo.taken_at).desc(),
            )
            .all()
        )

        return [
            {
                "key": f"{int(r.year)}-{str(int(r.month)).zfill(2)}",
                "year": int(r.year),
                "month": int(r.month),
                "count": r.count,
            }
            for r in rows
        ]

    def get_latest_ai_analysis(
        self,
        *,
        project_id: int,
        photo_id: int,
    ) -> Optional[PhotoAIAnalysis]:
        return (
            self.db.query(PhotoAIAnalysis)
            .filter(
                PhotoAIAnalysis.photo_id == photo_id,
                PhotoAIAnalysis.project_id == project_id,
            )
            .order_by(PhotoAIAnalysis.created_at.desc())
            .first()
        )
