from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, time as time_
import json
from typing import Optional

from sqlalchemy import and_, extract, func, or_
from sqlalchemy.orm import Session

from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from .folder_service import apply_folder_filter


class PhotoCursorError(ValueError):
    pass


@dataclass(frozen=True)
class PhotoCursorPage:
    total: int
    page: int
    page_size: int
    items: list[Photo]
    next_cursor: Optional[str]
    has_more: bool


@dataclass
class ProjectPhotosQueryService:
    db: Session

    def _base_query(
        self,
        *,
        project_id: int,
        date_from: Optional[date],
        date_to: Optional[date],
        folder_id: Optional[int],
        folder_scope: str,
    ):
        query = self.db.query(Photo).filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.status != "quarantined",
        )
        if date_from is not None:
            query = query.filter(
                Photo.taken_at >= datetime.combine(date_from, time_.min)
            )
        if date_to is not None:
            query = query.filter(
                Photo.taken_at < datetime.combine(date_to, time_.min)
            )
        if folder_id is not None:
            query = apply_folder_filter(
                query,
                self.db,
                project_id,
                folder_id,
                folder_scope,
            )
        return query

    @staticmethod
    def _ordered(query):
        return query.order_by(
            Photo.taken_at.desc().nullslast(),
            Photo.created_at.desc(),
            Photo.id.desc(),
        )

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

        base_query = self._base_query(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            folder_id=folder_id,
            folder_scope=folder_scope,
        )

        total = base_query.count()
        photos = (
            self._ordered(base_query)
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return total, photos

    def list_photos_cursor(
        self,
        *,
        project_id: int,
        cursor: Optional[str],
        page_size: int,
        date_from: Optional[date],
        date_to: Optional[date],
        folder_id: Optional[int],
        folder_scope: str,
    ) -> PhotoCursorPage:
        page_size = max(1, min(page_size, 100))
        filters = {
            "project_id": project_id,
            "page_size": page_size,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "folder_id": folder_id,
            "folder_scope": folder_scope,
        }
        base_query = self._base_query(
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            folder_id=folder_id,
            folder_scope=folder_scope,
        )

        if cursor:
            payload = self._decode_cursor(cursor)
            if payload.get("filters") != filters:
                raise PhotoCursorError("Photo cursor does not match the current filters")
            total = self._cursor_int(payload, "total", minimum=0)
            page = self._cursor_int(payload, "page", minimum=1) + 1
            photo_id = self._cursor_int(payload, "id", minimum=1)
            created_at = self._cursor_datetime(payload, "created_at")
            taken_at = self._cursor_datetime(payload, "taken_at", nullable=True)
            base_query = base_query.filter(
                self._cursor_predicate(
                    taken_at=taken_at,
                    created_at=created_at,
                    photo_id=photo_id,
                )
            )
        else:
            total = base_query.count()
            page = 1

        rows = self._ordered(base_query).limit(page_size + 1).all()
        has_more = len(rows) > page_size
        items = rows[:page_size]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = self._encode_cursor(
                {
                    "v": 1,
                    "filters": filters,
                    "total": total,
                    "page": page,
                    "taken_at": last.taken_at.isoformat() if last.taken_at else None,
                    "created_at": last.created_at.isoformat(),
                    "id": last.id,
                }
            )

        return PhotoCursorPage(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    @staticmethod
    def _cursor_predicate(
        *,
        taken_at: Optional[datetime],
        created_at: datetime,
        photo_id: int,
    ):
        created_tail = or_(
            Photo.created_at < created_at,
            and_(Photo.created_at == created_at, Photo.id < photo_id),
        )
        if taken_at is None:
            return and_(Photo.taken_at.is_(None), created_tail)
        return or_(
            Photo.taken_at < taken_at,
            and_(Photo.taken_at == taken_at, created_tail),
            Photo.taken_at.is_(None),
        )

    @staticmethod
    def _encode_cursor(payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> dict:
        if len(cursor) > 4096:
            raise PhotoCursorError("Invalid photo cursor")
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhotoCursorError("Invalid photo cursor") from exc
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise PhotoCursorError("Unsupported photo cursor")
        return payload

    @staticmethod
    def _cursor_int(payload: dict, key: str, *, minimum: int) -> int:
        value = payload.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise PhotoCursorError(f"Invalid photo cursor field: {key}")
        return value

    @staticmethod
    def _cursor_datetime(
        payload: dict,
        key: str,
        *,
        nullable: bool = False,
    ) -> Optional[datetime]:
        value = payload.get(key)
        if value is None and nullable:
            return None
        if not isinstance(value, str):
            raise PhotoCursorError(f"Invalid photo cursor field: {key}")
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise PhotoCursorError(f"Invalid photo cursor field: {key}") from exc

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
