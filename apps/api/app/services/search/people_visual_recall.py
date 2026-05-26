"""PeopleVisualRecallService — recall by people-structure semantics.

Focuses on non-name people queries like 合照 / 集体照 / 多人 / 单人照.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.query_understanding_service import SearchQueryPlan
from .types import EffectiveSearchSettings, SearchCandidate

logger = logging.getLogger(__name__)

_GROUP_PHOTO_TERMS: tuple[str, ...] = ("合照", "合影", "集体照", "多人", "多人合照", "多人合影", "全家福")
_SINGLE_PERSON_TERMS: tuple[str, ...] = ("单人照", "人像", "自拍")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _extract_semantic_list(raw_result: object, key: str) -> list[str]:
    if not isinstance(raw_result, dict):
        return []
    semantic = raw_result.get("semantic")
    if not isinstance(semantic, dict):
        return []
    values = semantic.get(key)
    if not isinstance(values, list):
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def derive_people_visual_terms(query_plan: SearchQueryPlan) -> tuple[list[str], int, list[str]]:
    lower_query = query_plan.original_query.lower()
    terms: list[str] = []
    facets: list[str] = []
    min_people_count = 1

    for term in _GROUP_PHOTO_TERMS:
        if term in query_plan.original_query or term.lower() in lower_query:
            terms.extend(["人物", "多人", "合照", "合影", "集体照"])
            facets.extend(["people", "group_photo"])
            min_people_count = max(min_people_count, 2)

    if "集体照" in query_plan.original_query:
        min_people_count = max(min_people_count, 3)

    for term in _SINGLE_PERSON_TERMS:
        if term in query_plan.original_query or term.lower() in lower_query:
            terms.extend(["人物", "单人照", "人像", "自拍"])
            facets.append("people")

    if query_plan.intent in ("people_search", "group_photo_search"):
        terms.extend([str(t).strip() for t in query_plan.exact_terms + query_plan.expanded_terms if str(t).strip()])
        if "group_photo" in query_plan.core_facets:
            facets.extend(["people", "group_photo"])
            min_people_count = max(min_people_count, 2)
        elif "people" in query_plan.core_facets:
            facets.append("people")

    return _dedupe_preserve_order(terms), min_people_count, _dedupe_preserve_order(facets)


class PeopleVisualRecallService:
    def __init__(self, db: Session, search_settings: EffectiveSearchSettings) -> None:
        self._db = db
        self._settings = search_settings

    def search(
        self,
        query_plan: SearchQueryPlan,
        *,
        project_id: int,
        folder_photo_subquery: Optional[Select] = None,
        constrained_photo_ids: Optional[set[int]] = None,
        limit: Optional[int] = None,
    ) -> list[SearchCandidate]:
        terms, min_people_count, facets = derive_people_visual_terms(query_plan)
        if not terms and not facets:
            return []

        top_k = limit if limit is not None else self._settings.keyword_top_k

        base_query = (
            self._db.query(PhotoAIAnalysis)
            .join(Photo, Photo.id == PhotoAIAnalysis.photo_id)
            .filter(Photo.deleted_at.is_(None))
            .filter(Photo.project_id == project_id, PhotoAIAnalysis.project_id == project_id)
            .filter(
                or_(
                    PhotoAIAnalysis.people_count >= min_people_count,
                    PhotoAIAnalysis.search_keywords.any("合照"),
                    PhotoAIAnalysis.search_keywords.any("合影"),
                    PhotoAIAnalysis.search_keywords.any("多人"),
                    PhotoAIAnalysis.activity_tags.any("合影"),
                    PhotoAIAnalysis.activity_tags.any("合照"),
                )
            )
        )

        if folder_photo_subquery is not None:
            base_query = base_query.filter(PhotoAIAnalysis.photo_id.in_(folder_photo_subquery))

        if constrained_photo_ids is not None:
            if not constrained_photo_ids:
                return []
            base_query = base_query.filter(PhotoAIAnalysis.photo_id.in_(constrained_photo_ids))

        rows = (
            base_query
            .order_by(PhotoAIAnalysis.updated_at.desc().nullslast(), PhotoAIAnalysis.created_at.desc())
            .limit(top_k)
            .all()
        )

        candidates: list[SearchCandidate] = []
        for ai in rows:
            semantic_concepts = _extract_semantic_list(ai.raw_result, "concepts")
            semantic_facets = _extract_semantic_list(ai.raw_result, "facets")
            tags = [str(v).strip() for v in (ai.search_keywords or []) if str(v).strip()]
            tags.extend([str(v).strip() for v in (ai.activity_tags or []) if str(v).strip()])

            hits = [term for term in terms if term in semantic_concepts or term in tags]
            facet_hits = [facet for facet in facets if facet in semantic_facets]
            if ai.people_count is not None and ai.people_count >= min_people_count:
                hits.append(f"people_count>={min_people_count}")

            if not hits and not facet_hits:
                continue

            score = min(1.0, 0.2 + 0.2 * len(_dedupe_preserve_order(hits + facet_hits)))
            matched = _dedupe_preserve_order(hits + facet_hits)
            candidates.append(
                SearchCandidate(
                    photo_id=ai.photo_id,
                    keyword_score=round(score, 6),
                    matched_tags=matched,
                    match_source=["people_visual"],
                    field_scores={"people_visual": round(score, 6)},
                    keyword_explain={
                        "people_visual_terms": terms,
                        "people_visual_facets": facets,
                        "matched_people_visual": matched,
                        "people_count": ai.people_count,
                    },
                    hit_tiers={"strong"},
                    term_level_hits={
                        "exact": [],
                        "strong": matched,
                        "support": [],
                        "weak": [],
                        "negative": [],
                    },
                )
            )

        candidates.sort(key=lambda c: c.keyword_score, reverse=True)
        logger.debug(
            "[people_visual_recall] project_id=%d terms=%s facets=%s min_people=%d candidates=%d",
            project_id,
            terms,
            facets,
            min_people_count,
            len(candidates),
        )
        return candidates
