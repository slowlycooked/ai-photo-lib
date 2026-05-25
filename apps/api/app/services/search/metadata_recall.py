"""MetadataRecallService — recall photos by Photo table EXIF / metadata fields.

This service filters the ``photos`` table directly using structured fields
(taken_at, gps_latitude, gps_longitude, camera_make, camera_model, iso, …)
without relying on AI analysis embeddings.

It is used for:
- metadata-only queries (e.g. "12月的照片", "iPhone拍的", "有GPS的")
- mixed queries where metadata reduces the candidate set before semantic search
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import extract, or_
from sqlalchemy.sql import Select
from sqlalchemy.orm import Session

from ...models.photo import Photo
from .types import SearchCandidate

logger = logging.getLogger(__name__)


class MetadataRecallService:
    """Filter photos by Photo-table metadata fields."""

    def __init__(self, db: Session, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    # ── Public API ─────────────────────────────────────────────────────────────

    def search(
        self,
        *,
        metadata_filters: dict,
        folder_photo_subquery: Optional[Select] = None,
        limit: int = 5000,
    ) -> list[SearchCandidate]:
        """Return SearchCandidates for photos matching *metadata_filters*.

        Results are ordered by ``taken_at DESC`` (newest first), then ``id DESC``.
        Each candidate has ``final_score=1.0``, ``evidence_level="A"``,
        ``match_source=["metadata"]``, and ``matched_tags`` = human-readable
        matched metadata terms from the query.
        """
        photo_ids = self._resolve_photo_ids(
            metadata_filters=metadata_filters,
            folder_photo_subquery=folder_photo_subquery,
            limit=limit,
        )
        meta_terms: list[str] = metadata_filters.get("matched_metadata_terms", [])
        return [
            SearchCandidate(
                photo_id=pid,
                final_score=1.0,
                evidence_level="A",
                match_source=["metadata"],
                matched_tags=list(meta_terms),
                score_breakdown={"metadata_filter": True},
            )
            for pid in photo_ids
        ]

    def resolve_photo_ids(
        self,
        metadata_filters: dict,
        folder_photo_subquery: Optional[Select] = None,
        limit: int = 50_000,
    ) -> set[int]:
        """Return set of photo IDs matching *metadata_filters* (no ordering)."""
        return set(
            self._resolve_photo_ids(
                metadata_filters=metadata_filters,
                folder_photo_subquery=folder_photo_subquery,
                limit=limit,
            )
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    def _resolve_photo_ids(
        self,
        metadata_filters: dict,
        folder_photo_subquery: Optional[Select] = None,
        limit: int = 50_000,
    ) -> list[int]:
        """Build and execute the metadata filter query; return ordered ID list."""
        q = self._db.query(Photo.id).filter(
            Photo.project_id == self._project_id,
            Photo.deleted_at.is_(None),
        )

        date_from = metadata_filters.get("date_from")
        date_to = metadata_filters.get("date_to")
        year = metadata_filters.get("year")
        month = metadata_filters.get("month")
        months: list[int] = metadata_filters.get("months") or []
        has_gps = metadata_filters.get("has_gps")
        camera_make = metadata_filters.get("camera_make")
        camera_model = metadata_filters.get("camera_model")
        iso_min = metadata_filters.get("iso_min")
        iso_max = metadata_filters.get("iso_max")
        place_terms: list[str] = metadata_filters.get("place_terms") or []

        # ── Date / time ────────────────────────────────────────────────────────
        if date_from and date_to:
            # Precise date range takes priority over individual year/month filters
            q = q.filter(
                Photo.taken_at >= date_from,
                Photo.taken_at < date_to,
            )
        elif year is not None:
            q = q.filter(extract("year", Photo.taken_at) == year)
            if month is not None:
                q = q.filter(extract("month", Photo.taken_at) == month)
        elif month is not None:
            q = q.filter(extract("month", Photo.taken_at) == month)
        elif months:
            q = q.filter(extract("month", Photo.taken_at).in_(months))

        # ── GPS ────────────────────────────────────────────────────────────────
        if has_gps is True:
            q = q.filter(
                Photo.gps_latitude.is_not(None),
                Photo.gps_longitude.is_not(None),
            )
        elif has_gps is False:
            q = q.filter(
                (Photo.gps_latitude.is_(None)) | (Photo.gps_longitude.is_(None))
            )

        # ── Camera ─────────────────────────────────────────────────────────────
        # When both make and model are set (e.g. Apple + iPhone) use OR so either
        # column is enough to match (handles "iPhone 14 Pro" entries from various
        # software that may store it differently).
        if camera_make and camera_model:
            q = q.filter(
                (Photo.camera_make.ilike(f"%{camera_make}%"))
                | (Photo.camera_model.ilike(f"%{camera_model}%"))
            )
        elif camera_make:
            q = q.filter(Photo.camera_make.ilike(f"%{camera_make}%"))
        elif camera_model:
            q = q.filter(Photo.camera_model.ilike(f"%{camera_model}%"))

        # ── ISO ────────────────────────────────────────────────────────────────
        if iso_min is not None:
            q = q.filter(Photo.iso >= iso_min)
        if iso_max is not None:
            q = q.filter(Photo.iso <= iso_max)

        # ── Place name filters ───────────────────────────────────────────────
        for place_term in place_terms:
            like = f"%{place_term}%"
            q = q.filter(
                or_(
                    Photo.country_name.ilike(like),
                    Photo.admin1.ilike(like),
                    Photo.admin2.ilike(like),
                    Photo.city.ilike(like),
                    Photo.district.ilike(like),
                    Photo.formatted_address.ilike(like),
                )
            )

        # ── Folder scope ───────────────────────────────────────────────────────
        if folder_photo_subquery is not None:
            q = q.filter(Photo.id.in_(folder_photo_subquery))

        # Order by newest first for natural chronological browsing
        q = q.order_by(
            Photo.taken_at.desc().nulls_last(),
            Photo.id.desc(),
        )

        rows = q.limit(limit).all()
        result = [row[0] for row in rows]

        logger.debug(
            "[MetadataRecallService] project=%s filters=%s matched=%d",
            self._project_id,
            {k: v for k, v in metadata_filters.items() if v not in (None, [], False, {})},
            len(result),
        )
        return result
