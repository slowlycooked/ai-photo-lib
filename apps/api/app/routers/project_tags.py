from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project

router = APIRouter(prefix="/projects", tags=["projects-tags"])


class _TagCount(BaseModel):
    tag: str
    count: int


class _TagsResponse(BaseModel):
    scene_tags: list[_TagCount]
    object_tags: list[_TagCount]
    activity_tags: list[_TagCount]
    quality_tags: list[_TagCount]
    search_keywords: list[_TagCount]


def _count_tags(
    db: Session, field: str, project_id: int, limit: int = 100
) -> list[_TagCount]:
    sql = text(
        f"SELECT unnest(paa.{field}) AS tag, COUNT(*) AS cnt "  # noqa: S608
        f"FROM photo_ai_analysis paa "
        f"WHERE paa.project_id = :pid AND paa.{field} IS NOT NULL "
        f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
    )
    rows = db.execute(sql, {"pid": project_id, "limit": limit}).fetchall()
    return [_TagCount(tag=r[0], count=r[1]) for r in rows]


@router.get("/{project_id}/tags", response_model=_TagsResponse)
def project_tags(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return per-category tag counts for a project."""
    return _TagsResponse(
        scene_tags=_count_tags(db, "scene_tags", project_id),
        object_tags=_count_tags(db, "object_tags", project_id),
        activity_tags=_count_tags(db, "activity_tags", project_id),
        quality_tags=_count_tags(db, "quality_tags", project_id),
        search_keywords=_count_tags(db, "search_keywords", project_id),
    )
