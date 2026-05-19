from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo

logger = logging.getLogger(__name__)

# Score weights per field
_WEIGHTS = {
    "caption": 3,
    "ocr_text": 5,
    "scene_tags": 4,
    "object_tags": 4,
    "activity_tags": 4,
    "search_keywords": 4,
    "quality_tags": 2,
    "location_clues": 2,
    "file_name": 1,
}

# Approximate max score per query term (for normalisation)
_MAX_PER_TERM = sum(_WEIGHTS.values())


def _build_any_match_filter(terms: List[str]):
    """Return an OR filter: photo matches if *any* term appears in *any* field."""
    per_term = []
    for term in terms:
        like = f"%{term}%"
        per_term.append(
            or_(
                PhotoAIAnalysis.caption.ilike(like),
                PhotoAIAnalysis.ocr_text.ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.scene_tags, " "), ""
                ).ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.object_tags, " "), ""
                ).ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.activity_tags, " "), ""
                ).ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.search_keywords, " "), ""
                ).ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.quality_tags, " "), ""
                ).ilike(like),
                func.coalesce(
                    func.array_to_string(PhotoAIAnalysis.location_clues, " "), ""
                ).ilike(like),
                Photo.file_name.ilike(like),
            )
        )
    return or_(*per_term)


def _score_result(
    photo: Photo, ai: PhotoAIAnalysis, terms: List[str]
) -> Tuple[float, List[str]]:
    """Score a (photo, ai) pair and collect matched tag strings."""
    raw = 0
    matched: set[str] = set()

    for term in terms:
        t = term.lower()

        if ai.caption and t in ai.caption.lower():
            raw += _WEIGHTS["caption"]

        if ai.ocr_text and t in ai.ocr_text.lower():
            raw += _WEIGHTS["ocr_text"]

        if photo.file_name and t in photo.file_name.lower():
            raw += _WEIGHTS["file_name"]

        for field, weight in (
            ("scene_tags", _WEIGHTS["scene_tags"]),
            ("object_tags", _WEIGHTS["object_tags"]),
            ("activity_tags", _WEIGHTS["activity_tags"]),
            ("search_keywords", _WEIGHTS["search_keywords"]),
            ("quality_tags", _WEIGHTS["quality_tags"]),
            ("location_clues", _WEIGHTS["location_clues"]),
        ):
            tags: list[str] | None = getattr(ai, field, None)
            if tags:
                for tag in tags:
                    if t in tag.lower():
                        raw += weight
                        matched.add(tag)

    max_possible = len(terms) * _MAX_PER_TERM
    score = round(min(raw / max_possible, 1.0), 4) if max_possible else 0.0
    return score, sorted(matched)


def search_photos(
    db: Session,
    query: str,
    page: int = 1,
    page_size: int = 50,
    project_id: Optional[int] = None,
) -> Tuple[int, list]:
    """Lightweight keyword search with in-Python scoring.

    Returns (total_count, page_items) where each item is a dict ready to
    be consumed by the SearchResultItem schema.
    """
    query = query.strip()
    if not query:
        return 0, []

    # Tokenise: split on whitespace; fall back to the whole query as one term
    terms = [t for t in query.split() if t] or [query]

    # Cap candidate fetch to avoid full-table scans on very broad queries
    MAX_CANDIDATES = 2000

    rows: list[tuple[Photo, PhotoAIAnalysis]] = (
        db.query(Photo, PhotoAIAnalysis)
        .join(PhotoAIAnalysis, PhotoAIAnalysis.photo_id == Photo.id)
        .filter(Photo.deleted_at.is_(None))
        .filter(_build_any_match_filter(terms))
        .filter(*([Photo.project_id == project_id] if project_id is not None else []))
        .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .limit(MAX_CANDIDATES)
        .all()
    )

    # Score in Python and sort descending
    scored = []
    for photo, ai in rows:
        score, matched_tags = _score_result(photo, ai, terms)
        if score > 0:
            scored.append(
                {
                    "photo_id": photo.id,
                    "file_name": photo.file_name,
                    "thumbnail_url": f"/api/photos/{photo.id}/thumbnail?v={int(photo.updated_at.timestamp()) if photo.updated_at else 0}",
                    "updated_at": photo.updated_at,
                    "taken_at": photo.taken_at,
                    "width": photo.width,
                    "height": photo.height,
                    "caption": ai.caption,
                    "matched_tags": matched_tags,
                    "score": score,
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)

    total = len(scored)
    offset = (page - 1) * page_size
    page_items = scored[offset : offset + page_size]

    return total, page_items
