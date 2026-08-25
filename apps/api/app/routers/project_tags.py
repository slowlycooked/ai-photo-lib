from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.project import Project
from ..schemas.tags import TagCount, TagsResponse
from ..services.search.result_cache import get_project_search_cache_epoch

router = APIRouter(prefix="/projects", tags=["projects-tags"])

TAG_FIELDS = (
    "scene_tags",
    "object_tags",
    "activity_tags",
    "quality_tags",
    "search_keywords",
    "location_clues",
)

_TAG_GROUP_CACHE_TTL_SECONDS = 300
_TAG_GROUP_CACHE_MAX_SIZE = 128
_TAG_GROUP_CACHE: (
    "OrderedDict[tuple[int, int, int], tuple[float, dict[str, list[TagCount]]]]"
) = OrderedDict()
_TAG_GROUP_CACHE_LOCK = threading.Lock()


def _empty_tag_groups() -> dict[str, list[TagCount]]:
    return {field: [] for field in TAG_FIELDS}


def _get_cached_tag_groups(
    cache_key: tuple[int, int, int],
) -> dict[str, list[TagCount]] | None:
    now = time.monotonic()
    with _TAG_GROUP_CACHE_LOCK:
        hit = _TAG_GROUP_CACHE.get(cache_key)
        if hit is None:
            return None
        created_at, groups = hit
        if now - created_at > _TAG_GROUP_CACHE_TTL_SECONDS:
            _TAG_GROUP_CACHE.pop(cache_key, None)
            return None
        _TAG_GROUP_CACHE.move_to_end(cache_key)
        return copy.deepcopy(groups)


def _put_cached_tag_groups(
    cache_key: tuple[int, int, int],
    groups: dict[str, list[TagCount]],
) -> None:
    with _TAG_GROUP_CACHE_LOCK:
        _TAG_GROUP_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(groups))
        _TAG_GROUP_CACHE.move_to_end(cache_key)
        while len(_TAG_GROUP_CACHE) > _TAG_GROUP_CACHE_MAX_SIZE:
            _TAG_GROUP_CACHE.popitem(last=False)


def _count_tag_groups(
    db: Session, project_id: int, limit: int = 100
) -> dict[str, list[TagCount]]:
    """Count all tag categories for a project, excluding deleted photos."""
    sql = text(
        """
        WITH expanded AS (
          SELECT tag_groups.category, unnested.tag, paa.photo_id
          FROM photo_ai_analysis paa
          JOIN photos p ON p.id = paa.photo_id AND p.project_id = paa.project_id
          CROSS JOIN LATERAL (
            VALUES
              ('scene_tags'::text, paa.scene_tags),
              ('object_tags'::text, paa.object_tags),
              ('activity_tags'::text, paa.activity_tags),
              ('quality_tags'::text, paa.quality_tags),
              ('search_keywords'::text, paa.search_keywords),
              ('location_clues'::text, paa.location_clues)
          ) AS tag_groups(category, tags)
          CROSS JOIN LATERAL unnest(tag_groups.tags) AS unnested(tag)
          WHERE paa.project_id = :pid
            AND p.deleted_at IS NULL
            AND unnested.tag IS NOT NULL
        ),
        counted AS (
          SELECT category, tag, COUNT(DISTINCT photo_id) AS cnt
          FROM expanded
          GROUP BY category, tag
        ),
        ranked AS (
          SELECT
            category,
            tag,
            cnt,
            ROW_NUMBER() OVER (PARTITION BY category ORDER BY cnt DESC, tag ASC) AS rank
          FROM counted
        )
        SELECT category, tag, cnt
        FROM ranked
        WHERE rank <= :limit
        ORDER BY category, rank
        """
    )
    rows = db.execute(sql, {"pid": project_id, "limit": limit}).fetchall()
    groups = _empty_tag_groups()
    for category, tag, count in rows:
        if category in groups:
            groups[category].append(TagCount(tag=tag, count=count))
    return groups


@router.get("/{project_id}/tags", response_model=TagsResponse)
def project_tags(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return per-category tag counts for a project."""
    limit = 100
    cache_epoch = get_project_search_cache_epoch(db, project_id)
    cache_key = (project_id, cache_epoch, limit)
    tag_groups = _get_cached_tag_groups(cache_key)
    if tag_groups is None:
        tag_groups = _count_tag_groups(db, project_id, limit=limit)
        _put_cached_tag_groups(cache_key, tag_groups)
    return TagsResponse(
        scene_tags=tag_groups["scene_tags"],
        object_tags=tag_groups["object_tags"],
        activity_tags=tag_groups["activity_tags"],
        quality_tags=tag_groups["quality_tags"],
        search_keywords=tag_groups["search_keywords"],
        location_clues=tag_groups["location_clues"],
    )
