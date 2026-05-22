"""TagFilterService — exact tag-based photo filtering.

Bypasses keyword/vector search entirely. Uses a PostgreSQL array-contains
query (:tag_value = ANY(paa.{tag_field})) so that the result set precisely
matches the count shown on the tags page.

For the SQLite test environment, falls back to a json_each() based filter.
"""
from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.folder_service import apply_folder_filter

logger = logging.getLogger(__name__)

# Whitelist of fields that may be used as tag filter targets.
ALLOWED_TAG_FIELDS: frozenset[str] = frozenset(
    {
        "scene_tags",
        "object_tags",
        "activity_tags",
        "quality_tags",
        "search_keywords",
        "location_clues",
    }
)


def tag_filter_photos(
    db: Session,
    *,
    project_id: int,
    tag_field: str,
    tag_value: str,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    page: int = 1,
    page_size: int = 50,
) -> tuple[int, list[dict], None]:
    """Return (total, items, None) for an exact tag filter query.

    ``items`` is a list of dicts matching the SearchResultItem schema.
    ``None`` is returned in place of a debug payload (not applicable here).

    Raises ``ValueError`` if ``tag_field`` is not in the allowed whitelist.
    """
    if tag_field not in ALLOWED_TAG_FIELDS:
        raise ValueError(
            f"tag_field {tag_field!r} is not allowed. "
            f"Allowed values: {sorted(ALLOWED_TAG_FIELDS)}"
        )

    try:
        dialect = db.bind.dialect.name  # type: ignore[union-attr]
    except Exception:
        dialect = "postgresql"  # safe default for production

    # Build the base query joining photos with AI analysis
    query_obj = (
        db.query(Photo, PhotoAIAnalysis)
        .join(
            PhotoAIAnalysis,
            (PhotoAIAnalysis.photo_id == Photo.id)
            & (PhotoAIAnalysis.project_id == Photo.project_id),
        )
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
    )

    # Apply tag filter — dialect-aware
    if dialect == "sqlite":
        # SQLite stores ARRAY columns as TEXT (JSON). Use json_each().
        # Reference the table by its name as it appears in the FROM clause.
        tag_filter_clause = sa.text(
            f"EXISTS ("  # noqa: S608
            f"  SELECT 1 FROM json_each(photo_ai_analysis.{tag_field}) "
            f"  WHERE value = :tv"
            f")"
        ).bindparams(tv=tag_value)
    else:
        # PostgreSQL: :tv = ANY(column)
        tag_filter_clause = sa.text(
            f":tv = ANY(photo_ai_analysis.{tag_field})"  # noqa: S608
        ).bindparams(tv=tag_value)

    query_obj = query_obj.filter(tag_filter_clause)

    # Apply folder filter if requested
    if folder_id is not None:
        photo_subq = db.query(Photo).filter(
            Photo.deleted_at.is_(None), Photo.project_id == project_id
        )
        photo_subq = apply_folder_filter(photo_subq, db, project_id, folder_id, folder_scope)
        allowed_ids = {p.id for p in photo_subq.all()}
        query_obj = query_obj.filter(Photo.id.in_(allowed_ids))

    # Deterministic ordering: most-recent first
    query_obj = query_obj.order_by(
        Photo.taken_at.desc().nulls_last(),
        Photo.created_at.desc(),
    )

    total = query_obj.count()
    if total == 0:
        return 0, [], None

    offset = (page - 1) * page_size
    rows = query_obj.offset(offset).limit(page_size).all()

    items: list[dict] = []
    for photo, ai in rows:
        thumb = (
            f"/api/projects/{project_id}/photos/{photo.id}/thumbnail"
            f"?v={int(photo.updated_at.timestamp()) if photo.updated_at else 0}"
        )
        items.append(
            {
                "photo_id": photo.id,
                "file_name": photo.file_name,
                "thumbnail_url": thumb,
                "updated_at": photo.updated_at,
                "taken_at": photo.taken_at,
                "width": photo.width,
                "height": photo.height,
                "caption": ai.caption if ai else None,
                "matched_tags": [tag_value],
                "score": 1.0,
            }
        )

    logger.debug(
        "tag_filter_photos project_id=%s field=%s value=%r total=%d page=%d",
        project_id,
        tag_field,
        tag_value,
        total,
        page,
    )

    return total, items, None
