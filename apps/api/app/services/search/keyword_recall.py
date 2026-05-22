"""KeywordRecallService — tier-aware keyword search against photo AI analysis fields.

Keyword scoring uses a three-tier multiplier:
  exact match     × 1.0  (user's original words)
  expanded match  × 0.7  (close synonyms)
  broad match     × 0.3  (generic category terms)

Field weights come from EffectiveSearchSettings.keyword_field_weights so they
are fully project-configurable with no hardcoded constants.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.folder_service import apply_folder_filter
from ...services.query_understanding_service import SearchQueryPlan
from .types import (
    BROAD_TERM_MULTIPLIER,
    EXACT_TERM_MULTIPLIER,
    EXPANDED_TERM_MULTIPLIER,
    DEFAULT_KEYWORD_FIELD_WEIGHTS,
    EffectiveSearchSettings,
    SearchCandidate,
)

logger = logging.getLogger(__name__)


def _build_any_match_filter(terms: list[str]):
    """Build OR filter matching any term across all keyword fields."""
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
    photo: Photo,
    ai: PhotoAIAnalysis,
    query_plan: SearchQueryPlan,
    field_weights: dict[str, float],
) -> tuple[float, list[str], dict]:
    """Score a photo against the query using tier-aware keyword scoring.

    Returns (score, matched_tags, field_explain).
    """
    weights = field_weights or DEFAULT_KEYWORD_FIELD_WEIGHTS

    # Build (term, tier_multiplier) list from all three tiers
    term_tiers: list[tuple[str, float]] = [
        (t, EXACT_TERM_MULTIPLIER) for t in query_plan.exact_terms
    ] + [
        (t, EXPANDED_TERM_MULTIPLIER) for t in query_plan.expanded_terms
    ] + [
        (t, BROAD_TERM_MULTIPLIER) for t in query_plan.broad_terms
    ]

    raw = 0.0
    matched: set[str] = set()
    field_explain: dict[str, list[str]] = {}

    for term, multiplier in term_tiers:
        t = term.lower()

        if ai.caption and t in ai.caption.lower():
            raw += weights.get("caption", 3.0) * multiplier
            field_explain.setdefault("caption", []).append(term)

        if ai.ocr_text and t in ai.ocr_text.lower():
            raw += weights.get("ocr_text", 5.0) * multiplier
            field_explain.setdefault("ocr_text", []).append(term)

        if photo.file_name and t in photo.file_name.lower():
            raw += weights.get("file_name", 1.0) * multiplier
            field_explain.setdefault("file_name", []).append(term)

        for field_name, weight_key in (
            ("scene_tags", "scene_tags"),
            ("object_tags", "object_tags"),
            ("activity_tags", "activity_tags"),
            ("search_keywords", "search_keywords"),
            ("quality_tags", "quality_tags"),
            ("location_clues", "location_clues"),
        ):
            tags: Optional[list[str]] = getattr(ai, field_name, None)
            if tags:
                w = weights.get(weight_key, 2.0) * multiplier
                for tag in tags:
                    if t in tag.lower():
                        raw += w
                        matched.add(tag)
                        field_explain.setdefault(field_name, []).append(tag)

    # Normalise by the maximum possible score (all exact terms hit every field)
    all_terms = query_plan.all_terms
    max_possible = len(all_terms) * sum(weights.values()) if all_terms else 1.0
    score = round(min(raw / max_possible, 1.0), 4) if max_possible else 0.0
    return score, sorted(matched), field_explain


class KeywordRecallService:
    """Perform keyword recall against AI analysis fields."""

    def __init__(
        self,
        db: Session,
        search_settings: EffectiveSearchSettings,
    ) -> None:
        self._db = db
        self._settings = search_settings

    def search(
        self,
        query_plan: SearchQueryPlan,
        *,
        project_id: int,
        folder_photo_ids: Optional[set[int]],
        limit: Optional[int] = None,
    ) -> list[SearchCandidate]:
        """Run keyword search and return scored candidates."""
        all_terms = query_plan.all_terms
        if not all_terms:
            return []

        top_k = limit if limit is not None else self._settings.keyword_top_k

        base_query = (
            self._db.query(Photo, PhotoAIAnalysis)
            .join(PhotoAIAnalysis, PhotoAIAnalysis.photo_id == Photo.id)
            .filter(Photo.deleted_at.is_(None))
            .filter(_build_any_match_filter(all_terms))
            .filter(
                Photo.project_id == project_id,
                PhotoAIAnalysis.project_id == project_id,
            )
        )

        if folder_photo_ids is not None:
            if not folder_photo_ids:
                return []
            base_query = base_query.filter(Photo.id.in_(folder_photo_ids))

        rows: list[tuple[Photo, PhotoAIAnalysis]] = (
            base_query
            .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
            .limit(top_k)
            .all()
        )

        candidates: list[SearchCandidate] = []
        for photo, ai in rows:
            score, matched_tags, field_explain = _score_result(
                photo, ai, query_plan, self._settings.keyword_field_weights
            )
            if score <= 0:
                continue
            candidates.append(
                SearchCandidate(
                    photo_id=photo.id,
                    keyword_score=score,
                    matched_tags=matched_tags,
                    match_source=["keyword"],
                    keyword_explain=field_explain,
                )
            )

        candidates.sort(key=lambda c: c.keyword_score, reverse=True)
        return candidates
