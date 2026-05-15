from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ai import PhotoAIAnalysis

router = APIRouter(prefix="/tags", tags=["tags"])


class TagCount(BaseModel):
    tag: str
    count: int


class TagsResponse(BaseModel):
    scene_tags: list[TagCount]
    object_tags: list[TagCount]
    activity_tags: list[TagCount]
    quality_tags: list[TagCount]
    search_keywords: list[TagCount]


def _count_array_field(db: Session, field_name: str, limit: int = 100) -> list[TagCount]:
    """Unnest an array column and count occurrences."""
    rows = db.execute(
        text(
            f"SELECT unnest({field_name}) AS tag, COUNT(*) AS cnt "
            f"FROM photo_ai_analysis WHERE {field_name} IS NOT NULL "
            f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
        ),
        {"limit": limit},
    ).fetchall()
    return [TagCount(tag=row[0], count=row[1]) for row in rows]


@router.get("", response_model=TagsResponse)
def list_tags(db: Session = Depends(get_db)):
    return TagsResponse(
        scene_tags=_count_array_field(db, "scene_tags"),
        object_tags=_count_array_field(db, "object_tags"),
        activity_tags=_count_array_field(db, "activity_tags"),
        quality_tags=_count_array_field(db, "quality_tags"),
        search_keywords=_count_array_field(db, "search_keywords"),
    )
