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

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...config import settings as global_settings
from ...models.ai import PhotoAIAnalysis
from ...services.embedding_client import EmbeddingRequestError
from ...services.folder_service import build_folder_photo_ids_subquery
from ...services.query_understanding_service import SearchQueryPlan, understand_query
from .debug import build_debug_payload
from .fusion import rrf_merge
from .keyword_recall import KeywordRecallService
from .metadata_recall import MetadataRecallService
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

# ── Core-facet evidence config ─────────────────────────────────────────────────
# For queries with time/lighting core facets (e.g. "夜景", "夜晚"),
# require at least one of these positive evidence terms in AI tags/caption.
_NIGHT_CORE_POSITIVE: frozenset[str] = frozenset({
    "夜晚", "夜色", "夜景", "晚上", "夜间", "黑夜",
    "灯光", "霓虹", "路灯", "暗光", "长曝光",
    "night", "nighttime", "evening", "dark",
})
# Negative evidence terms that indicate daytime/bright conditions
_NIGHT_CORE_NEGATIVE: frozenset[str] = frozenset({
    "白天", "日间", "阳光", "晴天", "蓝天", "日照",
    "sunlight", "daytime", "sunny", "bright",
})

_INDOOR_CORE_POSITIVE: frozenset[str] = frozenset({
    "室内", "屋内", "室内场景", "房间", "客厅", "卧室", "厨房", "餐厅",
    "家具", "沙发", "床", "椅子", "桌子", "书架", "柜子", "台灯",
    "indoor", "indoors", "interior", "living room", "bedroom", "kitchen",
})

_INDOOR_CORE_NEGATIVE: frozenset[str] = frozenset({
    "户外", "室外", "自然", "风景", "海边", "山地", "街道", "建筑外观",
    "outdoor", "outside", "landscape", "street", "exterior",
})

_INDOOR_RICH_FIELDS: tuple[str, ...] = (
    "caption",
    "scene_tags",
    "object_tags",
    "activity_tags",
)
_INDOOR_WEAK_ONLY_FIELDS: tuple[str, ...] = (
    "search_keywords",
    "location_clues",
)


def _is_explicit_indoor_query(query_plan: "SearchQueryPlan") -> bool:
    exact_lower = {t.lower() for t in query_plan.exact_terms}
    matched_lower = {t.lower() for t in query_plan.matched_keys}
    return (
        query_plan.filters.get("indoor_outdoor") == "indoor"
        and "scene" in query_plan.core_facets
        and bool({"室内", "indoor", "indoors"} & (exact_lower | matched_lower))
    )


def _indoor_core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional["PhotoAIAnalysis"],
    query_plan: "SearchQueryPlan",
    settings: EffectiveSearchSettings,
) -> tuple[bool, str]:
    if ai_analysis is None:
        if (
            settings.allow_vector_only_for_facet_query
            and candidate.vector_score >= settings.vector_strict_score
        ):
            return True, "indoor_vector_only_high_confidence"
        return False, "indoor_no_ai_analysis"

    rich_parts: list[str] = []
    weak_parts: list[str] = []
    for field_name in _INDOOR_RICH_FIELDS:
        value = getattr(ai_analysis, field_name, None)
        if isinstance(value, str) and value:
            rich_parts.append(value.lower())
        elif value:
            rich_parts.extend(str(item).lower() for item in value)
    for field_name in _INDOOR_WEAK_ONLY_FIELDS:
        value = getattr(ai_analysis, field_name, None)
        if value:
            weak_parts.extend(str(item).lower() for item in value)

    file_name_hits = " ".join(
        str(hit).lower() for hit in (candidate.keyword_explain or {}).get("file_name", [])
    )
    rich_text = " ".join(rich_parts + ([file_name_hits] if file_name_hits else []))
    weak_text = " ".join(weak_parts)
    combined_text = f"{rich_text} {weak_text}".strip()

    has_positive = any(term in rich_text for term in _INDOOR_CORE_POSITIVE)
    has_negative = any(term in combined_text for term in _INDOOR_CORE_NEGATIVE)
    weak_only_match = (
        not has_positive
        and any(field in (candidate.keyword_explain or {}) for field in _INDOOR_WEAK_ONLY_FIELDS)
    )

    if (
        settings.allow_vector_only_for_facet_query
        and candidate.vector_score >= settings.vector_strict_score
    ):
        if has_negative and not has_positive:
            return False, "indoor_negative_evidence"
        return True, "indoor_vector_high_confidence"

    if has_positive and not has_negative:
        return True, "indoor_positive_visual_evidence"
    if has_positive and has_negative:
        if candidate.evidence_level in ("A", "B"):
            return True, "indoor_conflicting_but_strong_keyword"
        return False, "indoor_conflicting_evidence"
    if weak_only_match:
        return False, "indoor_weak_tag_only"
    return False, "indoor_no_positive_visual_evidence"


def _core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional["PhotoAIAnalysis"],
    query_plan: "SearchQueryPlan",
    settings: EffectiveSearchSettings,
) -> tuple[bool, str]:
    """Check if a candidate satisfies core-facet evidence requirements.

    Returns (passes: bool, reason: str).

    For time/lighting facet queries (night scenes etc.):
    - Requires at least one positive night-evidence term in tags/caption, OR
      high-confidence vector match (score >= vector_strict_score).
    - Downgrades candidates that strongly match daytime-negative terms.
    """
    if _is_explicit_indoor_query(query_plan):
        return _indoor_core_facet_passes(candidate, ai_analysis, query_plan, settings)

    # Only apply when the query has time/lighting core facets
    core_facets = query_plan.core_facets
    if "time" not in core_facets and "lighting" not in core_facets:
        return True, ""

    # Check if this is a night query
    is_night_query = any(
        k in {"夜景", "夜晚", "晚上", "黑夜", "夜间", "夜色"}
        for k in query_plan.matched_keys
    )
    if not is_night_query:
        return True, ""

    # Allow if setting disables core facet matching
    require_core = getattr(settings, "require_core_facet_match", False)
    allow_vector_only = getattr(settings, "allow_vector_only_for_facet_query", True)

    # Collect all text evidence from the candidate's AI analysis
    if ai_analysis is None:
        if allow_vector_only and candidate.vector_score >= settings.vector_strict_score:
            return True, "vector_only_high_confidence"
        return False if require_core else True, "no_ai_analysis"

    all_text: list[str] = []
    for field_name in ("caption", "ocr_text"):
        v = getattr(ai_analysis, field_name, None) or ""
        if v:
            all_text.append(v.lower())
    for field_name in ("scene_tags", "object_tags", "activity_tags",
                       "search_keywords", "location_clues"):
        tags = getattr(ai_analysis, field_name, None) or []
        all_text.extend(t.lower() for t in tags)
    combined_text = " ".join(all_text)

    has_positive = any(term in combined_text for term in _NIGHT_CORE_POSITIVE)
    has_negative = any(term in combined_text for term in _NIGHT_CORE_NEGATIVE)

    # Strong vector alone counts if above strict threshold
    if allow_vector_only and candidate.vector_score >= settings.vector_strict_score:
        if has_negative and not has_positive:
            return False, f"night_negative_evidence={has_negative}"
        return True, "vector_high_confidence"

    if has_positive and not has_negative:
        return True, "night_positive_evidence"
    if has_positive and has_negative:
        # Conflicting — allow if evidence_level is A/B, otherwise filter
        if candidate.evidence_level in ("A", "B"):
            return True, "night_conflicting_but_strong_keyword"
        return False, "night_conflicting_evidence"
    if not has_positive:
        if require_core:
            return False, "night_no_positive_evidence"
        # Soft: allow only A/B level candidates through
        if candidate.evidence_level in ("A", "B"):
            return True, "night_no_evidence_but_strong_keyword"
        return False, "night_no_core_facet_evidence"

    return True, ""


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


def _resolve_folder_photo_subquery(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[Select]:
    return build_folder_photo_ids_subquery(db, project_id, folder_id, folder_scope)


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

    # ── Settings resolution (must happen BEFORE query understanding so that
    #    enable_query_understanding is respected) ───────────────────────────────
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

    # ── Query understanding (gated by per-project enable_query_understanding) ─
    if effective_settings.enable_query_understanding:
        query_plan = understand_query(query, project_id=project_id)
    else:
        # Plain query plan: treat the whole query as exact_terms only
        from ...services.query_understanding_service import SearchQueryPlan as _Plan
        query_plan = _Plan(
            original_query=query,
            normalized_query=query,
            exact_terms=[w for w in query.split() if w],
            intent="semantic_photo_search",
        )

    trace.append({
        "stage": "query_plan",
        "intent": query_plan.intent,
        "normalized_query": query_plan.normalized_query,
        "exact_terms": query_plan.exact_terms,
        "expanded_terms": query_plan.expanded_terms,
        "broad_terms": query_plan.broad_terms,
        "support_terms": query_plan.support_terms,
        "negative_terms": query_plan.negative_terms,
        "matched_keys": query_plan.matched_keys,
        "core_facets": query_plan.core_facets,
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

    # ── Resolve effective search mode ─────────────────────────────────────────
    # mode=auto → defer to project settings (OCR queries always keyword)
    if mode == "auto":
        if query_plan.intent == "ocr_text_search":
            effective_mode: SearchMode = "keyword"
        else:
            effective_mode = effective_settings.default_mode
    else:
        effective_mode = mode  # type: ignore[assignment]

    logger.debug(
        "[search] resolved mode=%s project_id=%s query=%r intent=%s",
        effective_mode, project_id, query, query_plan.intent,
    )

    folder_photo_subquery = (
        _resolve_folder_photo_subquery(
            db,
            project_id=project_id,
            folder_id=folder_id,
            folder_scope=folder_scope,
        )
        if project_id is not None
        else None
    )

    constrained_photo_ids: Optional[set[int]] = None

    if folder_id is not None:
        folder_count = (
            int(
                db.query(func.count())
                .select_from(folder_photo_subquery.subquery())
                .scalar()
                or 0
            )
            if folder_photo_subquery is not None
            else None
        )
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

    # ── Metadata filter (EXIF / Photo fields) ──────────────────────────────
    metadata_filters = query_plan.metadata_filters
    _mf_active = bool(
        metadata_filters.get("year")
        or metadata_filters.get("month")
        or metadata_filters.get("months")
        or metadata_filters.get("date_from")
        or (metadata_filters.get("has_gps") is not None)
        or metadata_filters.get("camera_make")
        or metadata_filters.get("camera_model")
        or (metadata_filters.get("iso_min") is not None)
        or (metadata_filters.get("iso_max") is not None)
        or metadata_filters.get("place_terms")
    )

    if _mf_active and project_id is not None:
        _meta_svc = MetadataRecallService(db, project_id)
        if metadata_filters.get("metadata_only"):
            # ── Metadata-only query: bypass keyword/vector recall entirely ────
            logger.debug("[search] path=metadata-only filters=%s", metadata_filters)
            meta_results = _meta_svc.search(
                metadata_filters=metadata_filters,
                folder_photo_subquery=folder_photo_subquery,
            )
            total, items = build_result_items(
                db,
                meta_results,
                project_id=project_id,
                mode="hybrid",  # uses final_score
                page=page,
                page_size=page_size,
                debug=debug,
            )
            trace.append({
                "stage": "metadata_filter",
                "path": "metadata-only",
                "filters": {k: v for k, v in metadata_filters.items() if v not in (None, [], False, {})},
                "matched_count": len(meta_results),
            })
            trace.append({
                "stage": "result",
                "path": "metadata-only",
                "total": total,
                "items_in_page": len(items),
                "page": page,
            })
            debug_payload: Optional[dict] = None
            if debug:
                debug_payload = build_debug_payload(
                    query_plan=query_plan,
                    mode="metadata",
                    embedding_model="",
                    embedding_dimension=global_settings.embedding_dimension,
                    keyword_candidates=0,
                    vector_candidates=0,
                    merged_candidates=len(meta_results),
                    fallback_reason="",
                    settings=effective_settings,
                    trace=trace,
                    metadata_filters=metadata_filters,
                    metadata_candidates=len(meta_results),
                    metadata_only=True,
                )
            logger.debug(
                "[search] ── DONE ── path=metadata-only total=%d items=%d page=%d",
                total, len(items), page,
            )
            return total, items, debug_payload
        else:
            # ── Mixed: restrict keyword/vector recall to metadata-filtered IDs ──
            _meta_ids = _meta_svc.resolve_photo_ids(
                metadata_filters=metadata_filters,
                folder_photo_subquery=folder_photo_subquery,
            )
            logger.debug(
                "[search] metadata_filter (mixed) matched=%d", len(_meta_ids)
            )
            trace.append({
                "stage": "metadata_filter",
                "path": "mixed",
                "filters": {k: v for k, v in metadata_filters.items() if v not in (None, [], False, {})},
                "matched_count": len(_meta_ids),
            })
            constrained_photo_ids = _meta_ids

    kw_service = KeywordRecallService(db, effective_settings)
    keyword_results = kw_service.search(
        query_plan,
        project_id=project_id or 0,
        folder_photo_subquery=folder_photo_subquery,
        constrained_photo_ids=constrained_photo_ids,
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
    stale_embedding_filtered = 0

    is_ocr_query = query_plan.intent == "ocr_text_search"
    vec_service = VectorRecallService(db, effective_settings)

    logger.debug(
        "[search] vector_recall start is_ocr=%s project_id=%s",
        is_ocr_query, project_id,
    )
    try:
        vector_scores, embedding_model, fallback_reason, stale_embedding_filtered = vec_service.search(
            query=query,
            normalized_query=query_plan.normalized_query,
            is_ocr_query=is_ocr_query,
            project_id=project_id,  # type: ignore[arg-type]
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
        )
        trace.append({
            "stage": "vector_recall",
            "candidates": len(vector_scores),
            "embedding_model": embedding_model,
            "is_ocr": is_ocr_query,
            "stale_embedding_filtered": stale_embedding_filtered,
        })
        logger.debug(
            "[search] vector_recall done candidates=%d embedding_model=%s stale_filtered=%d",
            len(vector_scores), embedding_model, stale_embedding_filtered,
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

    # ── Core facet evidence validator ─────────────────────────────────────────
    # For queries with strong intent facets (time/lighting/weather/animal),
    # require supporting evidence in AI tags or high-confidence vector score.
    core_facet_filtered = 0
    if merged and query_plan.core_facets and project_id is not None:
        photo_ids_for_facet = [c.photo_id for c in merged]
        ai_rows_for_facet = (
            db.query(PhotoAIAnalysis)
            .filter(
                PhotoAIAnalysis.photo_id.in_(photo_ids_for_facet),
                PhotoAIAnalysis.project_id == project_id,
            )
            .all()
        )
        ai_by_id_facet: dict[int, PhotoAIAnalysis] = {
            r.photo_id: r for r in ai_rows_for_facet
        }
        kept_facet: list[SearchCandidate] = []
        for c in merged:
            ai_obj = ai_by_id_facet.get(c.photo_id)
            passes, reason = _core_facet_passes(c, ai_obj, query_plan, effective_settings)
            if passes:
                kept_facet.append(c)
            else:
                core_facet_filtered += 1
                c.filter_reason = f"core_facet_fail:{reason}"
                filtered_out.append(c)
        if core_facet_filtered:
            logger.debug(
                "[search] core_facet_filter removed %d candidates (%d remaining)",
                core_facet_filtered, len(kept_facet),
            )
            merged = kept_facet
        trace.append({
            "stage": "core_facet_filter",
            "core_facets": query_plan.core_facets,
            "matched_keys": query_plan.matched_keys,
            "filtered": core_facet_filtered,
            "remaining": len(merged),
        })

    filtered_count += core_facet_filtered

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
        # Build a small sample of filtered-out candidates for debug
        _filtered_samples = [
            {
                "photo_id": c.photo_id,
                "evidence_level": c.evidence_level,
                "filter_reason": c.filter_reason,
                "vector_score": round(c.vector_score, 4),
                "keyword_score": round(c.keyword_score, 4),
            }
            for c in filtered_out[:10]
        ]
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
            filtered_out_samples=_filtered_samples,
            stale_embedding_filtered=stale_embedding_filtered,
        )
    logger.debug(
        "[search] ── DONE ── path=hybrid total=%d items=%d page=%d",
        total, len(items), page,
    )
    return total, items, debug_payload
