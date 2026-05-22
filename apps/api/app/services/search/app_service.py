"""SearchService (new package) — the main entry point for photo search.

Orchestrates:
  1. SearchSettingsResolver → EffectiveSearchSettings
  2. understand_query (query understanding)
  3. folder filter resolution
  4. KeywordRecallService
  5. VectorRecallService
  6. RRF fusion
  7. ResultHydrator
  8. DebugPayload builder

For backward compatibility, ``search_photos()`` is also exposed as a
top-level function via ``apps/api/app/services/search_service.py``.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...config import settings as global_settings
from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.embedding_client import EmbeddingRequestError
from ...services.folder_service import apply_folder_filter
from ...services.query_understanding_service import SearchQueryPlan, understand_query
from .debug import build_debug_payload
from .fusion import rrf_merge
from .keyword_recall import KeywordRecallService
from .result_hydrator import build_result_items
from .settings_resolver import SearchSettingsResolver
from .types import (
    EVIDENCE_SCORE_MAP,
    EffectiveSearchSettings,
    SearchCandidate,
    SearchMode,
    VectorMatchScores,
    evidence_level_passes,
)
from .vector_recall import VectorRecallService

logger = logging.getLogger(__name__)

# ── Evidence level constants ──────────────────────────────────────────────────

_EVIDENCE_LEVEL_RANK_REASONS: dict[str, str] = {
    "A": "exact query term matched in keyword fields",
    "B": "strong/expanded term matched in keyword fields",
    "C": "strict vector match OR support term + moderate vector",
    "D": "support/weak keyword only or moderate vector (0.25-strict)",
    "E": "weak vector signal only — filtered by default",
    "F": "negative/conflicting term hit without strong positive evidence",
}

# Normal vector threshold for support-assisted C (below vector_strict_score)
_VECTOR_NORMAL_THRESHOLD = 0.32


def _compute_evidence_level(
    candidate: SearchCandidate,
    settings: Optional[EffectiveSearchSettings] = None,
) -> str:
    """Classify a merged candidate into evidence level A–F.

    A  exact query term matched in keyword fields
    B  strong (expanded) term matched — no exact
    C  vector >= vector_strict_score (default 0.42)
       OR (support term hit AND vector >= 0.32)
    D  support-only hit, weak-only hit, or 0.25 <= vector < strict
    E  very low vector only — no keyword evidence
    F  negative/conflicting term hit without A/B positive evidence
    """
    hit_tiers = candidate.hit_tiers  # {"exact","strong","support","weak","negative"}
    vector_strict = settings.vector_strict_score if settings else 0.42
    vector_normal = _VECTOR_NORMAL_THRESHOLD

    if "exact" in hit_tiers:
        return "A"
    if "strong" in hit_tiers:
        return "B"

    # F level: negative hit with no strong positive keyword evidence
    if "negative" in hit_tiers and candidate.vector_score < vector_normal:
        return "F"

    # C level: strict vector OR support-assisted
    if candidate.vector_score >= vector_strict:
        return "C"
    if "support" in hit_tiers and candidate.vector_score >= vector_normal:
        return "C"

    # D level: some positive evidence but not strong enough for C
    if "support" in hit_tiers or "weak" in hit_tiers:
        return "D"
    if candidate.vector_score >= 0.25:
        return "D"

    # E: very weak vector, no keyword evidence
    if candidate.vector_score > 0:
        return "E"
    return "E"


def _apply_evidence_scoring(
    candidates: list[SearchCandidate],
    settings: EffectiveSearchSettings,
) -> list[SearchCandidate]:
    """Apply evidence-level bonus/penalty to final_score and record score_breakdown.

    Adjusts final_score by ``evidence_score × evidence_weight`` and subtracts
    ``negative_term_penalty`` per negative term hit (if enabled).
    """
    for c in candidates:
        level = c.evidence_level or "E"
        ev_score = EVIDENCE_SCORE_MAP.get(level, 0.0)
        bonus = ev_score * settings.evidence_weight

        neg_penalty = 0.0
        if settings.enable_negative_penalty and "negative" in c.hit_tiers:
            neg_hits = len(c.term_level_hits.get("negative", []))
            neg_penalty = neg_hits * settings.negative_term_penalty

        old_score = c.final_score
        c.final_score = max(0.0, old_score + bonus - neg_penalty)
        c.score_breakdown = {
            "rrf_score": round(c.rrf_score, 6),
            "pre_evidence_final": round(old_score, 6),
            "evidence_level": level,
            "evidence_bonus": round(bonus, 6),
            "negative_penalty": round(neg_penalty, 6),
            "final_score": round(c.final_score, 6),
        }

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    return candidates


def _apply_semantic_tag_boost(
    db: Session,
    candidates: list[SearchCandidate],
    query_plan: SearchQueryPlan,
    project_id: int,
) -> list[SearchCandidate]:
    """Post-RRF score adjustment using direct tag matching.

    - Expanded (strong) term hits in tags → strong boost (+0.04 per term)
    - Broad (weak) term hits in tags → weak boost (+0.01 per term)
    - Penalise_tags hits → penalty (-0.03 per tag found)

    Results are re-sorted by final_score after adjustment.
    """
    if not candidates:
        return candidates

    photo_ids = [c.photo_id for c in candidates]
    rows = (
        db.query(PhotoAIAnalysis)
        .filter(
            PhotoAIAnalysis.photo_id.in_(photo_ids),
            PhotoAIAnalysis.project_id == project_id,
        )
        .all()
    )
    ai_by_id: dict[int, PhotoAIAnalysis] = {r.photo_id: r for r in rows}

    expanded_lower = {t.lower() for t in query_plan.expanded_terms}
    support_lower = {t.lower() for t in query_plan.support_terms}
    broad_lower = {t.lower() for t in query_plan.broad_terms}
    penalize_lower = {t.lower() for t in query_plan.penalize_tags}

    _TAG_FIELDS = ("scene_tags", "object_tags", "activity_tags", "search_keywords")

    for c in candidates:
        ai = ai_by_id.get(c.photo_id)
        if ai is None:
            continue

        all_tags_lower: list[str] = []
        for field_name in _TAG_FIELDS:
            tags = getattr(ai, field_name, None) or []
            all_tags_lower.extend(t.lower() for t in tags)

        boost = 0.0
        for tag in all_tags_lower:
            if any(e in tag for e in expanded_lower):
                boost += 0.04
            elif any(s in tag for s in support_lower):
                boost += 0.02
            elif any(b in tag for b in broad_lower):
                boost += 0.01
            if penalize_lower and any(p in tag for p in penalize_lower):
                boost -= 0.03

        if boost != 0.0:
            c.final_score = max(0.0, c.final_score + boost)

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    logger.debug(
        "[semantic_tag_boost] applied to %d candidates "
        "expanded=%d broad=%d penalize=%d",
        len(candidates),
        len(expanded_lower),
        len(broad_lower),
        len(penalize_lower),
    )
    return candidates


def _resolve_folder_photo_ids(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[set[int]]:
    if folder_id is None:
        return None
    photo_query = db.query(Photo).filter(
        Photo.deleted_at.is_(None), Photo.project_id == project_id
    )
    photo_query = apply_folder_filter(photo_query, db, project_id, folder_id, folder_scope)
    return {p.id for p in photo_query.all()}


def search_photos(
    db: Session,
    query: str,
    page: int = 1,
    page_size: int = 50,
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    mode: SearchMode = "hybrid",
    debug: bool = False,
) -> tuple[int, list, Optional[dict]]:
    """Search photos using project-configurable hybrid search.

    Returns (total, items, debug_payload).
    """
    query = query.strip()
    if not query:
        return 0, [], None

    # ── Trace collector (always populated; only included in response when debug=True) ─
    trace: list[dict] = []
    trace.append({
        "stage": "input",
        "query": query,
        "mode": mode,
        "page": page,
        "page_size": page_size,
        "folder_id": folder_id,
        "folder_scope": folder_scope,
    })

    logger.debug(
        "[search] ── START ── project_id=%s query=%r mode=%s page=%d page_size=%d folder_id=%s folder_scope=%s",
        project_id, query, mode, page, page_size, folder_id, folder_scope,
    )

    # Query understanding
    query_plan = understand_query(query, project_id=project_id)

    trace.append({
        "stage": "query_plan",
        "intent": query_plan.intent,
        "normalized_query": query_plan.normalized_query,
        "exact_terms": query_plan.exact_terms,
        "expanded_terms": query_plan.expanded_terms,
        "broad_terms": query_plan.broad_terms,
        "recommended_profile": query_plan.recommended_profile,
    })
    logger.debug(
        "[search] query_plan intent=%s exact=%s expanded=%s broad=%s normalized=%r",
        query_plan.intent,
        query_plan.exact_terms,
        query_plan.expanded_terms,
        query_plan.broad_terms,
        query_plan.normalized_query,
    )

    # Settings resolution
    if project_id is not None:
        effective_settings: EffectiveSearchSettings = SearchSettingsResolver.resolve(
            db, project_id
        )
    else:
        effective_settings = SearchSettingsResolver.defaults()

    trace.append({
        "stage": "settings",
        "default_mode": effective_settings.default_mode,
        "keyword_top_k": effective_settings.keyword_top_k,
        "vector_top_k": effective_settings.vector_top_k,
        "rrf_k": effective_settings.rrf_k,
        "keyword_weight": effective_settings.keyword_weight,
        "vector_weight": effective_settings.vector_weight,
        "vector_min_score": effective_settings.vector_min_score,
        "enable_query_understanding": effective_settings.enable_query_understanding,
        "enable_structured_filters": effective_settings.enable_structured_filters,
        "enable_semantic_tag_boost": effective_settings.enable_semantic_tag_boost,
    })
    logger.debug(
        "[search] effective_settings default_mode=%s kw_top_k=%d vec_top_k=%d "
        "rrf_k=%d kw_weight=%.2f vec_weight=%.2f vec_min_score=%.4f "
        "enable_qu=%s enable_filters=%s enable_tag_boost=%s",
        effective_settings.default_mode,
        effective_settings.keyword_top_k,
        effective_settings.vector_top_k,
        effective_settings.rrf_k,
        effective_settings.keyword_weight,
        effective_settings.vector_weight,
        effective_settings.vector_min_score,
        effective_settings.enable_query_understanding,
        effective_settings.enable_structured_filters,
        effective_settings.enable_semantic_tag_boost,
    )

    # Respect caller's mode override; skip QU mode suggestion here
    effective_mode: SearchMode = mode

    logger.debug(
        "[search] resolved mode=%s project_id=%s query=%r intent=%s",
        effective_mode, project_id, query, query_plan.intent,
    )

    folder_photo_ids = (
        _resolve_folder_photo_ids(
            db,
            project_id=project_id,
            folder_id=folder_id,
            folder_scope=folder_scope,
        )
        if project_id is not None
        else None
    )

    if folder_id is not None:
        folder_count = len(folder_photo_ids) if folder_photo_ids is not None else None
        trace.append({
            "stage": "folder_filter",
            "folder_id": folder_id,
            "scope": folder_scope,
            "photo_ids_count": folder_count,
        })
        logger.debug(
            "[search] folder_filter folder_id=%s scope=%s photo_ids_count=%s",
            folder_id, folder_scope, folder_count,
        )

    # Keyword recall (always run — needed for hybrid fallback)
    kw_service = KeywordRecallService(db, effective_settings)
    keyword_results = kw_service.search(
        query_plan,
        project_id=project_id or 0,
        folder_photo_ids=folder_photo_ids,
    )

    trace.append({
        "stage": "keyword_recall",
        "candidates": len(keyword_results),
        "top_scores": [round(c.keyword_score, 4) for c in keyword_results[:5]],
    })
    logger.debug(
        "[search] keyword_recall candidates=%d top_scores=%s",
        len(keyword_results),
        [round(c.keyword_score, 4) for c in keyword_results[:5]],
    )

    # ── Keyword-only mode ─────────────────────────────────────────────────────
    if effective_mode == "keyword" or project_id is None:
        logger.debug("[search] path=keyword-only")
        total, items = build_result_items(
            db,
            keyword_results,
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace.append({"stage": "result", "path": "keyword-only", "total": total, "items_in_page": len(items), "page": page})
        debug_payload: Optional[dict] = None
        if debug:
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="keyword",
                embedding_model="",
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason="",
                settings=effective_settings,
                trace=trace,
            )
        logger.debug(
            "[search] ── DONE ── path=keyword-only total=%d items=%d page=%d",
            total, len(items), page,
        )
        return total, items, debug_payload

    # ── Vector / hybrid path ──────────────────────────────────────────────────
    vector_scores: dict[int, VectorMatchScores] = {}
    embedding_model = ""
    fallback_reason = ""

    is_ocr_query = query_plan.intent == "ocr_text_search"
    vec_service = VectorRecallService(db, effective_settings)

    logger.debug(
        "[search] vector_recall start is_ocr=%s project_id=%s",
        is_ocr_query, project_id,
    )
    try:
        vector_scores, embedding_model, fallback_reason = vec_service.search(
            query=query,
            normalized_query=query_plan.normalized_query,
            is_ocr_query=is_ocr_query,
            project_id=project_id,  # type: ignore[arg-type]
            folder_photo_ids=folder_photo_ids,
        )
        trace.append({
            "stage": "vector_recall",
            "candidates": len(vector_scores),
            "embedding_model": embedding_model,
            "is_ocr": is_ocr_query,
        })
        logger.debug(
            "[search] vector_recall done candidates=%d embedding_model=%s",
            len(vector_scores), embedding_model,
        )
    except (EmbeddingRequestError, SQLAlchemyError, RuntimeError) as exc:
        fallback_reason = str(exc)
        trace.append({
            "stage": "vector_recall",
            "error": fallback_reason,
            "fallback": True,
        })
        logger.warning(
            "Vector search fallback to keyword. project_id=%s query=%r error=%s",
            project_id,
            query,
            exc,
        )
        if isinstance(exc, SQLAlchemyError):
            try:
                db.rollback()
            except Exception:
                pass
        if effective_mode == "vector":
            trace.append({"stage": "result", "path": "vector-error", "total": 0, "items_in_page": 0, "page": page})
            debug_payload = None
            if debug:
                debug_payload = build_debug_payload(
                    query_plan=query_plan,
                    mode="vector",
                    embedding_model=embedding_model,
                    embedding_dimension=global_settings.embedding_dimension,
                    keyword_candidates=len(keyword_results),
                    vector_candidates=0,
                    merged_candidates=0,
                    fallback_reason=fallback_reason,
                    settings=effective_settings,
                    trace=trace,
                )
            return 0, [], debug_payload
        # hybrid falls back to keyword-only
        total, items = build_result_items(
            db,
            keyword_results,
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace.append({"stage": "result", "path": "hybrid-kw-fallback", "total": total, "items_in_page": len(items), "page": page})
        debug_payload = None
        if debug:
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="hybrid",
                embedding_model=embedding_model,
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason=fallback_reason,
                settings=effective_settings,
                trace=trace,
            )
        return total, items, debug_payload

    # ── Vector-only mode ──────────────────────────────────────────────────────
    if effective_mode == "vector":
        logger.debug("[search] path=vector-only")
        vector_only: list[SearchCandidate] = [
            SearchCandidate(
                photo_id=photo_id,
                vector_score=scores.total_score,
                final_score=scores.total_score,
                match_source=[
                    src
                    for src, val in (
                        ("vector_content", scores.content_score),
                        ("vector_caption", scores.caption_score),
                        ("vector_tag", scores.tag_score),
                        ("vector_ocr", scores.ocr_score),
                    )
                    if val > 0
                ],
                field_scores={
                    "content": round(scores.content_score, 4),
                    "caption": round(scores.caption_score, 4),
                    "tag": round(scores.tag_score, 4),
                    "ocr": round(scores.ocr_score, 4),
                },
                vector_explain={
                    "content": round(scores.content_score, 4),
                    "caption": round(scores.caption_score, 4),
                    "tag": round(scores.tag_score, 4),
                    "ocr": round(scores.ocr_score, 4),
                },
            )
            for photo_id, scores in sorted(
                vector_scores.items(), key=lambda x: x[1].total_score, reverse=True
            )
        ]
        total, items = build_result_items(
            db,
            vector_only,
            project_id=project_id or 0,
            mode="vector",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace.append({
            "stage": "result",
            "path": "vector-only",
            "total": total,
            "items_in_page": len(items),
            "page": page,
        })
        debug_payload = None
        if debug:
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="vector",
                embedding_model=embedding_model,
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=len(vector_scores),
                merged_candidates=len(vector_only),
                fallback_reason="",
                settings=effective_settings,
                trace=trace,
            )
        return total, items, debug_payload

    # ── Hybrid: RRF merge ─────────────────────────────────────────────────────
    logger.debug(
        "[search] path=hybrid rrf_merge kw_candidates=%d vec_candidates=%d",
        len(keyword_results), len(vector_scores),
    )
    merged = rrf_merge(keyword_results, vector_scores, effective_settings)
    logger.debug(
        "[search] rrf_merge done merged=%d top_final_scores=%s",
        len(merged),
        [round(c.final_score, 6) for c in merged[:5]],
    )
    trace.append({
        "stage": "rrf_merge",
        "kw_candidates": len(keyword_results),
        "vec_candidates": len(vector_scores),
        "merged": len(merged),
        "top_final_scores": [round(c.final_score, 6) for c in merged[:5]],
        "rrf_k": effective_settings.rrf_k,
        "kw_weight": effective_settings.keyword_weight,
        "vec_weight": effective_settings.vector_weight,
    })

    # ── Evidence level computation, scoring adjustment, and filtering ─────────
    for c in merged:
        c.evidence_level = _compute_evidence_level(c, effective_settings)

    if effective_settings.enable_evidence_filter:
        merged = _apply_evidence_scoring(merged, effective_settings)

    pre_filter_count = len(merged)
    min_level = effective_settings.min_display_evidence_level
    filtered_out: list[SearchCandidate] = []
    kept: list[SearchCandidate] = []
    for c in merged:
        if evidence_level_passes(c.evidence_level or "E", min_level):
            kept.append(c)
        else:
            c.filter_reason = (
                f"evidence_level:{c.evidence_level} below min:{min_level}"
            )
            filtered_out.append(c)
    merged = kept
    filtered_count = pre_filter_count - len(merged)

    if filtered_count:
        logger.debug(
            "[search] evidence_filter removed %d candidates below level %s (%d remaining)",
            filtered_count, min_level, len(merged),
        )
    trace.append({
        "stage": "evidence_filter",
        "pre_filter": pre_filter_count,
        "min_display_level": min_level,
        "filtered_count": filtered_count,
        "remaining": len(merged),
        "level_distribution": {
            lvl: sum(1 for c in merged if c.evidence_level == lvl)
            for lvl in ("A", "B", "C", "D", "E", "F")
        },
        "filtered_level_distribution": {
            lvl: sum(1 for c in filtered_out if c.evidence_level == lvl)
            for lvl in ("D", "E", "F")
        },
    })

    # ── P3: Semantic tag boost (if enabled for project) ───────────────────────
    if effective_settings.enable_semantic_tag_boost and merged and project_id is not None:
        merged = _apply_semantic_tag_boost(db, merged, query_plan, project_id)
        trace.append({
            "stage": "semantic_tag_boost",
            "candidates": len(merged),
            "top_final_scores": [round(c.final_score, 6) for c in merged[:5]],
            "penalize_tags": query_plan.penalize_tags,
        })
        logger.debug(
            "[search] semantic_tag_boost applied penalize_tags=%s",
            query_plan.penalize_tags,
        )

    total, items = build_result_items(
        db,
        merged,
        project_id=project_id or 0,
        mode="hybrid",
        page=page,
        page_size=page_size,
        debug=debug,
    )
    trace.append({"stage": "result", "path": "hybrid", "total": total, "items_in_page": len(items), "page": page})
    debug_payload = None
    if debug:
        debug_payload = build_debug_payload(
            query_plan=query_plan,
            mode="hybrid",
            embedding_model=embedding_model,
            embedding_dimension=global_settings.embedding_dimension,
            keyword_candidates=len(keyword_results),
            vector_candidates=len(vector_scores),
            merged_candidates=len(merged),
            fallback_reason="",
            settings=effective_settings,
            trace=trace,
            displayed_candidates=total,
            filtered_candidates=filtered_count,
        )
    logger.debug(
        "[search] ── DONE ── path=hybrid total=%d items=%d page=%d",
        total, len(items), page,
    )
    return total, items, debug_payload
