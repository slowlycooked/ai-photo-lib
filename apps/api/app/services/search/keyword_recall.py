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
from sqlalchemy.sql import Select
from sqlalchemy.orm import Session

from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.folder_service import apply_folder_filter
from ...services.query_understanding_service import SearchQueryPlan
from ...services.tag_localization import expand_term_aliases
from .types import (
    BROAD_TERM_MULTIPLIER,
    EXACT_TERM_MULTIPLIER,
    EXPANDED_TERM_MULTIPLIER,
    SUPPORT_TERM_MULTIPLIER,
    DEFAULT_KEYWORD_FIELD_WEIGHTS,
    EffectiveSearchSettings,
    SearchCandidate,
)

logger = logging.getLogger(__name__)

_ANIMAL_SCORE_FLOOR = 0.65

# 这些短语包含动物字符但语义是活动，不应触发 animal_search 的分数兜底
# 与 query_understanding_service._ACTIVITY_PHRASE_OVERRIDES 保持同步
_ANIMAL_FLOOR_ACTIVITY_EXCLUSIONS: frozenset[str] = frozenset({
    "钓鱼", "垂钓", "捕鱼", "捞鱼", "摸鱼",
    "骑马", "赛马", "驯马", "马术",
    "斗鸡", "放鸟", "牧羊",
})


def _build_any_match_filter(terms: list[str]):
    """Build OR filter matching any term across all keyword fields."""
    per_term = []
    for term in terms:
        alias_filters = []
        for alias in expand_term_aliases(term):
            like = f"%{alias}%"
            alias_filters.append(
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
        per_term.append(or_(*alias_filters))
    return or_(*per_term)


def _score_result(
    photo: Photo,
    ai: PhotoAIAnalysis,
    query_plan: SearchQueryPlan,
    field_weights: dict[str, float],
) -> tuple[float, list[str], dict, set, dict]:
    """Score a photo against the query using five-tier keyword scoring.

    Returns (score, matched_tags, field_explain, hit_tiers, term_level_hits).

    Tier multipliers:
      exact / must     × 1.0
      strong / expanded× 0.7
      support          × 0.5  (context clues — present in scoring but NOT recall)
      weak / broad     × 0.3
      negative         tracked separately (penalised in app_service)

    hit_tiers: set of tier names that had at least one match.
      {"exact", "strong", "support", "weak", "negative"}

    term_level_hits: per-tier list of matched query terms.
    """
    weights = field_weights or DEFAULT_KEYWORD_FIELD_WEIGHTS

    # Build (term, tier_name, tier_multiplier) list
    # Note: support_terms and broad_terms are scored here even though they
    # don't trigger recall — they still contribute a boost if the photo was
    # recalled by stronger evidence.
    term_tiers: list[tuple[str, str, float]] = (
        [(t, "exact", EXACT_TERM_MULTIPLIER) for t in query_plan.exact_terms]
        + [(t, "strong", EXPANDED_TERM_MULTIPLIER) for t in query_plan.expanded_terms]
        + [(t, "support", SUPPORT_TERM_MULTIPLIER) for t in query_plan.support_terms]
        + [(t, "weak", BROAD_TERM_MULTIPLIER) for t in query_plan.broad_terms]
    )

    raw = 0.0
    matched: set[str] = set()
    field_explain: dict[str, list[str]] = {}
    hit_tiers: set[str] = set()
    term_level_hits: dict[str, list[str]] = {
        "exact": [], "strong": [], "support": [], "weak": [], "negative": [],
    }

    for term, tier_name, multiplier in term_tiers:
        aliases = [alias.lower() for alias in expand_term_aliases(term)]
        matched_this_term = False

        if ai.caption and any(alias in ai.caption.lower() for alias in aliases):
            raw += weights.get("caption", 3.0) * multiplier
            field_explain.setdefault("caption", []).append(term)
            matched_this_term = True

        if ai.ocr_text and any(alias in ai.ocr_text.lower() for alias in aliases):
            raw += weights.get("ocr_text", 5.0) * multiplier
            field_explain.setdefault("ocr_text", []).append(term)
            matched_this_term = True

        if photo.file_name and any(alias in photo.file_name.lower() for alias in aliases):
            raw += weights.get("file_name", 1.0) * multiplier
            field_explain.setdefault("file_name", []).append(term)
            matched_this_term = True

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
                    lowered_tag = tag.lower()
                    if any(alias in lowered_tag for alias in aliases):
                        raw += w
                        matched.add(tag)
                        field_explain.setdefault(field_name, []).append(tag)
                        matched_this_term = True

        if matched_this_term:
            hit_tiers.add(tier_name)
            hits_for_tier = term_level_hits[tier_name]
            if term not in hits_for_tier:
                hits_for_tier.append(term)

    # Track negative term hits (no score change here — penalised in app_service)
    for neg_term in query_plan.negative_terms:
        aliases = [alias.lower() for alias in expand_term_aliases(neg_term)]
        neg_hit = False
        if ai.caption and any(alias in ai.caption.lower() for alias in aliases):
            neg_hit = True
        if not neg_hit and ai.ocr_text and any(alias in ai.ocr_text.lower() for alias in aliases):
            neg_hit = True
        if not neg_hit:
            for field_name in ("scene_tags", "object_tags", "activity_tags",
                               "search_keywords", "location_clues"):
                tags = getattr(ai, field_name, None)
                if tags and any(any(alias in tag.lower() for alias in aliases) for tag in tags):
                    neg_hit = True
                    break
        if neg_hit:
            hit_tiers.add("negative")
            if neg_term not in term_level_hits["negative"]:
                term_level_hits["negative"].append(neg_term)

    # Normalise by the maximum possible score
    # (all non-negative terms hitting every field at exact multiplier)
    all_positive_terms = query_plan.all_terms  # includes support + weak
    max_possible = len(all_positive_terms) * sum(weights.values()) if all_positive_terms else 1.0
    score = round(min(raw / max_possible, 1.0), 4) if max_possible else 0.0

    if query_plan.intent == "animal_search" and term_level_hits["strong"]:
        strong_entity_fields = {"caption", "object_tags", "search_keywords"}
        if any(field in field_explain for field in strong_entity_fields):
            # 仅当 exact_terms 中不包含活动短语时才应用分数兜底
            # 防止因 intent 在之前的分类器中被错误分类时误抬高分数
            exact_lower_set = {t.lower() for t in query_plan.exact_terms}
            if not any(t in _ANIMAL_FLOOR_ACTIVITY_EXCLUSIONS for t in exact_lower_set):
                score = max(score, _ANIMAL_SCORE_FLOOR)

    return score, sorted(matched), field_explain, hit_tiers, term_level_hits


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
        folder_photo_subquery: Optional[Select],
        constrained_photo_ids: Optional[set[int]] = None,
        limit: Optional[int] = None,
    ) -> list[SearchCandidate]:
        """Run keyword search and return scored candidates.

        P1: Only exact_terms + expanded_terms (strong) are used in the SQL
        WHERE filter.  broad_terms (weak) may still contribute to score when
        a photo is already retrieved by stronger evidence, but they can never
        be the *sole* reason a photo enters the recall set.
        """
        # P1: recall filter uses only exact + expanded (strong) terms
        recall_terms = query_plan.recall_terms
        if not recall_terms:
            logger.debug("[keyword_recall] no recall_terms after query plan, returning empty")
            return []

        top_k = limit if limit is not None else self._settings.keyword_top_k
        scan_limit = max(top_k, min(top_k * 5, 10_000))

        logger.debug(
            "[keyword_recall] start project_id=%d top_k=%d scan_limit=%d "
            "exact=%s expanded=%s broad=%s (broad excluded from SQL filter)",
            project_id, top_k, scan_limit,
            query_plan.exact_terms,
            query_plan.expanded_terms,
            query_plan.broad_terms,
        )

        base_query = (
            self._db.query(Photo, PhotoAIAnalysis)
            .join(PhotoAIAnalysis, PhotoAIAnalysis.photo_id == Photo.id)
            .filter(Photo.deleted_at.is_(None))
            .filter(_build_any_match_filter(recall_terms))  # P1: weak terms excluded
            .filter(
                Photo.project_id == project_id,
                PhotoAIAnalysis.project_id == project_id,
            )
        )

        if folder_photo_subquery is not None:
            base_query = base_query.filter(Photo.id.in_(folder_photo_subquery))

        if constrained_photo_ids is not None:
            if not constrained_photo_ids:
                logger.debug("[keyword_recall] constrained_photo_ids is empty set, returning empty")
                return []
            base_query = base_query.filter(Photo.id.in_(constrained_photo_ids))

        rows: list[tuple[Photo, PhotoAIAnalysis]] = (
            base_query
            .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
            .limit(scan_limit)
            .all()
        )

        logger.debug(
            "[keyword_recall] db_rows=%d (scan_limit=%d final_top_k=%d)",
            len(rows),
            scan_limit,
            top_k,
        )

        candidates: list[SearchCandidate] = []
        zero_score_count = 0
        for photo, ai in rows:
            score, matched_tags, field_explain, hit_tiers, term_level_hits = _score_result(
                photo, ai, query_plan, self._settings.keyword_field_weights
            )
            if score <= 0:
                zero_score_count += 1
                continue
            candidates.append(
                SearchCandidate(
                    photo_id=photo.id,
                    keyword_score=score,
                    matched_tags=matched_tags,
                    match_source=["keyword"],
                    keyword_explain=field_explain,
                    hit_tiers=hit_tiers,
                    term_level_hits=term_level_hits,
                )
            )

        candidates.sort(key=lambda c: c.keyword_score, reverse=True)
        logger.debug(
            "[keyword_recall] done scored=%d zero_score_skipped=%d top_scores=%s",
            len(candidates),
            zero_score_count,
            [round(c.keyword_score, 4) for c in candidates[:5]],
        )
        if candidates and logger.isEnabledFor(5):  # TRACE level
            for c in candidates[:10]:
                logger.log(5, "[keyword_recall] photo_id=%d score=%.4f hit_tiers=%s explain=%s", c.photo_id, c.keyword_score, c.hit_tiers, c.keyword_explain)
        return candidates[:top_k]
