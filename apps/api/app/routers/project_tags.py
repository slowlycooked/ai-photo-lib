from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.tags import TagCount, TagsResponse

router = APIRouter(prefix="/projects", tags=["projects-tags"])


def _count_tags(
    db: Session, field: str, project_id: int, limit: int = 100
) -> list[TagCount]:
    """Count tags for a project, excluding deleted photos."""
    sql = text(
        f"SELECT tag, COUNT(DISTINCT t.photo_id) AS cnt "  # noqa: S608
        f"FROM ("
        f"  SELECT paa.photo_id, unnest(paa.{field}) AS tag"
        f"  FROM photo_ai_analysis paa"
        f"  JOIN photos p ON p.id = paa.photo_id AND p.project_id = paa.project_id"
        f"  WHERE paa.project_id = :pid AND paa.{field} IS NOT NULL"
        f"    AND p.deleted_at IS NULL"
        f") t "
        f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
    )
    rows = db.execute(sql, {"pid": project_id, "limit": limit}).fetchall()
    return [TagCount(tag=r[0], count=r[1]) for r in rows]


@router.get("/{project_id}/tags", response_model=TagsResponse)
def project_tags(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return per-category tag counts for a project."""
    return TagsResponse(
        scene_tags=_count_tags(db, "scene_tags", project_id),
        object_tags=_count_tags(db, "object_tags", project_id),
        activity_tags=_count_tags(db, "activity_tags", project_id),
        quality_tags=_count_tags(db, "quality_tags", project_id),
        search_keywords=_count_tags(db, "search_keywords", project_id),
        location_clues=_count_tags(db, "location_clues", project_id),
    )
