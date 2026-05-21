from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.tags import TagCount, TagsResponse

logger = logging.getLogger(__name__)

# DEPRECATED: Use /projects/{project_id}/tags instead.
router = APIRouter(prefix="/tags", tags=["tags [deprecated]"])

_DEPRECATION_MSG = (
    "Global /tags endpoint is deprecated. "
    "Use /projects/{project_id}/tags instead."
)


def _count_array_field(
    db: Session,
    field_name: str,
    limit: int = 100,
    project_id: Optional[int] = None,
) -> list[TagCount]:
    """Unnest an array column and count occurrences, optionally filtered by project."""
    if project_id is not None:
        sql = text(
            f"SELECT unnest(paa.{field_name}) AS tag, COUNT(*) AS cnt "
            f"FROM photo_ai_analysis paa "
            f"JOIN photos p ON paa.photo_id = p.id "
            f"WHERE paa.{field_name} IS NOT NULL AND p.project_id = :project_id "
            f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
        )
        rows = db.execute(sql, {"limit": limit, "project_id": project_id}).fetchall()
    else:
        sql = text(
            f"SELECT unnest({field_name}) AS tag, COUNT(*) AS cnt "
            f"FROM photo_ai_analysis WHERE {field_name} IS NOT NULL "
            f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
        )
        rows = db.execute(sql, {"limit": limit}).fetchall()
    return [TagCount(tag=row[0], count=row[1]) for row in rows]


@router.get("", response_model=TagsResponse, deprecated=True)
def list_tags(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """[DEPRECATED] Use GET /projects/{project_id}/tags instead."""
    logger.warning(_DEPRECATION_MSG)
    return TagsResponse(
        scene_tags=_count_array_field(db, "scene_tags", project_id=project_id),
        object_tags=_count_array_field(db, "object_tags", project_id=project_id),
        activity_tags=_count_array_field(db, "activity_tags", project_id=project_id),
        quality_tags=_count_array_field(db, "quality_tags", project_id=project_id),
        search_keywords=_count_array_field(db, "search_keywords", project_id=project_id),
    )
