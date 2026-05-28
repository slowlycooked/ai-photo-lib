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

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...config import settings as global_settings
from ...models.ai import PhotoAIAnalysis
from ...models.face import FaceDetection, Person, PersonFaceAssignment
from ...services.embedding_client import EmbeddingRequestError
from ...services.folder_service import build_folder_photo_ids_subquery
from ...services.query_understanding_service import understand_query
from .concept_recall import ConceptRecallService, derive_concept_query_context
from .debug import SearchDebugContext, build_logged_debug_payload
from .execution_context import SearchExecutionContext
from .filter_policy import (
    apply_evidence_scoring as apply_evidence_scoring_policy,
    apply_semantic_tag_boost as apply_semantic_tag_boost_policy,
    compute_evidence_level as compute_evidence_level_policy,
    core_facet_passes as core_facet_passes_policy,
    resolve_face_filter_photo_ids as resolve_face_filter_photo_ids_policy,
)
from .fusion import fuse_hybrid_candidates
from .keyword_recall import KeywordRecallService
from .metadata_recall import MetadataRecallService
from .people_query_resolver import PeopleQueryResolution, resolve_people_query
from .people_visual_recall import PeopleVisualRecallService
from .people_recall import PeopleRecallService
from .post_fusion_pipeline import apply_post_fusion_pipeline
from .query_understanding import (
    SearchQueryPlan,
    build_query_plan_trace_event,
    resolve_search_query_plan,
)
from .recall_pipeline import (
    run_keyword_auxiliary_stage,
    run_metadata_stage,
    run_people_stage,
    run_vector_stage,
)
from .result_hydrator import (
    build_empty_result_response,
    build_result_items,
    build_result_response,
)
from .search_plan_builder import build_search_plan
from .settings_resolver import SearchSettingsResolver
from .trace_writer import SearchDebugTraceWriter
from .types import (
    EffectiveSearchSettings,
    SearchCandidate,
    SearchMode,
    VectorMatchScores,
)
from .vector_recall import VectorRecallService

logger = logging.getLogger(__name__)

_PEOPLE_RRF_WEIGHT = 1.20

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

_ANIMAL_ENTITY_HINTS: frozenset[str] = frozenset({
    "猫", "小猫", "猫咪", "狗", "小狗", "狗狗", "鸟", "小鸟", "飞鸟", "禽鸟",
    "马", "骏马", "鹿", "梅花鹿", "野鹿", "兔", "兔子", "小兔", "鱼", "水族",
    "蝴蝶", "昆虫",
})

_ANIMAL_GENERIC_TERMS: frozenset[str] = frozenset({
    "动物", "宠物", "野生动物", "动物园", "小动物", "animal", "野外",
})

_METADATA_ONLY_BLOCKED_INTENTS: frozenset[str] = frozenset({
    "animal_search",
    "people_search",
    "group_photo_search",
    "food_search",
    "weather_search",
    "activity_search",
    "semantic_photo_search",
})


def _is_explicit_indoor_query(query_plan: "SearchQueryPlan") -> bool:
    exact_lower = {t.lower() for t in query_plan.exact_terms}
    matched_lower = {t.lower() for t in query_plan.matched_keys}
    return (
        query_plan.filters.get("indoor_outdoor") == "indoor"
        and "scene" in query_plan.core_facets
        and bool({"室内", "indoor", "indoors"} & (exact_lower | matched_lower))
    )


def _animal_core_facet_passes(
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
            return True, "animal_vector_only_high_confidence"
        return False, "animal_no_ai_analysis"

    rich_parts: list[str] = []
    weak_parts: list[str] = []

    for field_name in ("caption", "object_tags", "search_keywords", "semantic_concepts"):
        value = getattr(ai_analysis, field_name, None)
        if isinstance(value, str) and value:
            rich_parts.append(value.lower())
        elif value:
            rich_parts.extend(str(item).lower() for item in value)

    for field_name in ("scene_tags", "location_clues"):
        value = getattr(ai_analysis, field_name, None)
        if value:
            weak_parts.extend(str(item).lower() for item in value)

    raw_result = getattr(ai_analysis, "raw_result", None)
    if isinstance(raw_result, dict):
        animals = raw_result.get("animals") or []
        rich_parts.extend(str(item).lower() for item in animals if str(item).strip())

    rich_text = " ".join(rich_parts)
    weak_text = " ".join(weak_parts)

    entity_terms = [
        term.lower()
        for term in (query_plan.exact_terms + query_plan.expanded_terms)
        if term.lower() not in _ANIMAL_GENERIC_TERMS
    ]
    positive_terms = entity_terms or list(_ANIMAL_ENTITY_HINTS)

    # ── Precise entity check ───────────────────────────────────────────────
    # Use exact tag-set membership for structured fields to prevent single-char
    # terms (e.g. "鱼") from matching unrelated text via substring containment.
    # For caption / semantic_concepts, require at least 2 chars to avoid
    # false positives from single-character words.

    # Build exact tag set from structured array fields
    entity_tag_set: set[str] = set()
    for field_name in ("object_tags", "search_keywords"):
        tags = getattr(ai_analysis, field_name, None) or []
        entity_tag_set.update(t.lower().strip() for t in tags if str(t).strip())

    # Also include raw_result.animals as exact tags
    raw_result = getattr(ai_analysis, "raw_result", None)
    if isinstance(raw_result, dict):
        for item in (raw_result.get("animals") or []):
            val = str(item).lower().strip()
            if val:
                entity_tag_set.add(val)

    # Free-text fields: only match terms with length >= 2 to avoid single-char noise
    caption_text = (getattr(ai_analysis, "caption", None) or "").lower()
    semantic_c = [
        str(v).lower().strip()
        for v in (getattr(ai_analysis, "semantic_concepts", None) or [])
        if str(v).strip()
    ]
    semantic_text = " ".join(semantic_c)

    has_positive = (
        any(term in entity_tag_set for term in positive_terms)
        or any(len(term) >= 2 and term in caption_text for term in positive_terms)
        or any(len(term) >= 2 and term in semantic_text for term in positive_terms)
    )

    weak_scene_only = any(term in weak_text for term in ("动物园", "宠物店")) and not has_positive

    if (
        settings.allow_vector_only_for_facet_query
        and candidate.vector_score >= settings.vector_strict_score
    ):
        return True, "animal_vector_high_confidence"

    if has_positive:
        return True, "animal_entity_evidence"
    if weak_scene_only:
        return False, "animal_scene_without_entity"
    return False, "animal_no_entity_evidence"


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
    return core_facet_passes_policy(candidate, ai_analysis, query_plan, settings)


def _compute_evidence_level(
    candidate: SearchCandidate,
    settings: Optional[EffectiveSearchSettings] = None,
) -> str:
    return compute_evidence_level_policy(candidate, settings)


def _apply_evidence_scoring(
    candidates: list[SearchCandidate],
    settings: EffectiveSearchSettings,
) -> list[SearchCandidate]:
    return apply_evidence_scoring_policy(candidates, settings)


def _apply_semantic_tag_boost(
    db: Session,
    candidates: list[SearchCandidate],
    query_plan: SearchQueryPlan,
    project_id: int,
) -> list[SearchCandidate]:
    boosted = apply_semantic_tag_boost_policy(db, candidates, query_plan, project_id)
    logger.debug(
        "[semantic_tag_boost] applied to %d candidates expanded=%d broad=%d penalize=%d",
        len(boosted),
        len(query_plan.expanded_terms),
        len(query_plan.broad_terms),
        len(query_plan.penalize_tags),
    )
    return boosted


def _resolve_folder_photo_subquery(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[Select]:
    return build_folder_photo_ids_subquery(db, project_id, folder_id, folder_scope)


def _resolve_face_filter_photo_ids(
    db: Session,
    *,
    project_id: int,
    face_count_min: Optional[int],
    face_count_max: Optional[int],
    has_review_pending: Optional[bool],
    has_unnamed_people: Optional[bool],
) -> set[int]:
    return resolve_face_filter_photo_ids_policy(
        db,
        project_id=project_id,
        face_count_min=face_count_min,
        face_count_max=face_count_max,
        has_review_pending=has_review_pending,
        has_unnamed_people=has_unnamed_people,
    )


def _attach_people_explain(
    candidates: list[SearchCandidate],
    people_results: list[SearchCandidate],
) -> list[SearchCandidate]:
    """Attach people explain payload to existing candidate rows by photo_id."""
    if not candidates or not people_results:
        return candidates
    by_photo = {c.photo_id: c for c in people_results}
    for candidate in candidates:
        people_hit = by_photo.get(candidate.photo_id)
        if not people_hit:
            continue
        candidate.people_score = people_hit.people_score
        candidate.people_rank = people_hit.people_rank
        candidate.people_explain = dict(people_hit.people_explain)
        if "people" not in candidate.match_source:
            candidate.match_source.append("people")
    return candidates


def _merge_keyword_with_aux_candidates(
    keyword_results: list[SearchCandidate],
    aux_results: list[SearchCandidate],
    *,
    aux_source: str,
) -> list[SearchCandidate]:
    if not aux_results:
        return keyword_results

    merged_by_photo: dict[int, SearchCandidate] = {c.photo_id: c for c in keyword_results}

    for aux in aux_results:
        existing = merged_by_photo.get(aux.photo_id)
        if existing is None:
            merged_by_photo[aux.photo_id] = aux
            continue

        existing.keyword_score = max(existing.keyword_score, aux.keyword_score)
        existing.matched_tags = sorted(set(existing.matched_tags) | set(aux.matched_tags))
        existing.hit_tiers = existing.hit_tiers | aux.hit_tiers

        if aux_source not in existing.match_source:
            existing.match_source.append(aux_source)

        for field_name, values in aux.keyword_explain.items():
            current = existing.keyword_explain.setdefault(field_name, [])
            for value in values:
                if value not in current:
                    current.append(value)

        for tier, terms in aux.term_level_hits.items():
            current = existing.term_level_hits.setdefault(tier, [])
            for term in terms:
                if term not in current:
                    current.append(term)

    merged = sorted(merged_by_photo.values(), key=lambda c: c.keyword_score, reverse=True)
    return merged


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
    face_count_min: Optional[int] = None,
    face_count_max: Optional[int] = None,
    has_review_pending: Optional[bool] = None,
    has_unnamed_people: Optional[bool] = None,
) -> tuple[int, list, Optional[dict]]:
    """Search photos using project-configurable hybrid search.

    Returns (total, items, debug_payload).
    """
    query = query.strip()
    if not query:
        return 0, [], None

    # ── Trace collector (always populated; only included in response when debug=True) ─
    trace: list[dict] = []
    trace_writer = SearchDebugTraceWriter(trace)
    trace_writer.write_stage(
        "input",
        query=query,
        mode=mode,
        page=page,
        page_size=page_size,
        folder_id=folder_id,
        folder_scope=folder_scope,
    )

    logger.debug(
        "[search] ── START ── project_id=%s query=%r mode=%s page=%d page_size=%d folder_id=%s folder_scope=%s",
        project_id, query, mode, page, page_size, folder_id, folder_scope,
    )

    face_filter_active = (
        face_count_min is not None
        or face_count_max is not None
        or has_review_pending is not None
        or has_unnamed_people is not None
    )

    plan = build_search_plan(
        db,
        query=query,
        mode=mode,
        project_id=project_id,
        face_filter_active=face_filter_active,
        settings_resolver_cls=SearchSettingsResolver,
        query_plan_resolver=resolve_search_query_plan,
        understander=understand_query,
        people_query_resolver=resolve_people_query,
        people_resolution_cls=PeopleQueryResolution,
    )
    execution_context = SearchExecutionContext.from_plan(
        plan,
        trace,
        project_id=project_id,
    )

    trace_writer.write_stage(
        "settings",
        default_mode=execution_context.effective_settings.default_mode,
        keyword_top_k=execution_context.effective_settings.keyword_top_k,
        vector_top_k=execution_context.effective_settings.vector_top_k,
        rrf_k=execution_context.effective_settings.rrf_k,
        keyword_weight=execution_context.effective_settings.keyword_weight,
        vector_weight=execution_context.effective_settings.vector_weight,
        vector_min_score=execution_context.effective_settings.vector_min_score,
        enable_query_understanding=execution_context.effective_settings.enable_query_understanding,
        enable_structured_filters=execution_context.effective_settings.enable_structured_filters,
        enable_semantic_tag_boost=execution_context.effective_settings.enable_semantic_tag_boost,
    )
    trace_writer.write(build_query_plan_trace_event(execution_context.query_plan))
    trace_writer.write_stage(
        "people_query",
        has_people=execution_context.people_resolution.has_people,
        people_filter_mode=execution_context.people_resolution.people_filter_mode,
        matched_person_ids=execution_context.people_resolution.matched_person_ids,
        residual_query=execution_context.people_resolution.residual_query,
        is_people_only=execution_context.people_resolution.is_people_only,
    )
    if execution_context.people_resolution.has_people and execution_context.people_resolution.residual_query.strip():
        trace_writer.write(
            build_query_plan_trace_event(
                execution_context.search_query_plan,
                stage="query_plan_effective",
                include_recommended_profile=False,
            )
        )

    logger.debug(
        "[search] effective_settings default_mode=%s kw_top_k=%d vec_top_k=%d "
        "rrf_k=%d kw_weight=%.2f vec_weight=%.2f vec_min_score=%.4f "
        "enable_qu=%s enable_filters=%s enable_tag_boost=%s",
        execution_context.effective_settings.default_mode,
        execution_context.effective_settings.keyword_top_k,
        execution_context.effective_settings.vector_top_k,
        execution_context.effective_settings.rrf_k,
        execution_context.effective_settings.keyword_weight,
        execution_context.effective_settings.vector_weight,
        execution_context.effective_settings.vector_min_score,
        execution_context.effective_settings.enable_query_understanding,
        execution_context.effective_settings.enable_structured_filters,
        execution_context.effective_settings.enable_semantic_tag_boost,
    )
    logger.debug(
        "[search] query_plan intent=%s exact=%s expanded=%s broad=%s normalized=%r",
        execution_context.query_plan.intent,
        execution_context.query_plan.exact_terms,
        execution_context.query_plan.expanded_terms,
        execution_context.query_plan.broad_terms,
        execution_context.query_plan.normalized_query,
    )
    logger.debug(
        "[search] people_query has_people=%s mode=%s matched_person_ids=%s residual=%r",
        execution_context.people_resolution.has_people,
        execution_context.people_resolution.people_filter_mode,
        execution_context.people_resolution.matched_person_ids,
        execution_context.people_resolution.residual_query,
    )

    logger.debug(
        "[search] resolved mode=%s project_id=%s query=%r intent=%s",
        execution_context.effective_mode, project_id, query, execution_context.search_query_plan.intent,
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
    execution_context.folder_photo_subquery = folder_photo_subquery

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
        trace_writer.write_stage(
            "folder_filter",
            folder_id=folder_id,
            scope=folder_scope,
            photo_ids_count=folder_count,
        )
        logger.debug(
            "[search] folder_filter folder_id=%s scope=%s photo_ids_count=%s",
            folder_id, folder_scope, folder_count,
        )

    face_filter_photo_ids: Optional[set[int]] = None
    if project_id is not None and face_filter_active:
        face_filter_photo_ids = _resolve_face_filter_photo_ids(
            db,
            project_id=project_id,
            face_count_min=face_count_min,
            face_count_max=face_count_max,
            has_review_pending=has_review_pending,
            has_unnamed_people=has_unnamed_people,
        )
        execution_context.constrained_photo_ids = (
            set(face_filter_photo_ids)
            if execution_context.constrained_photo_ids is None
            else execution_context.constrained_photo_ids & face_filter_photo_ids
        )
        trace_writer.write_stage(
            "face_filter",
            face_count_min=face_count_min,
            face_count_max=face_count_max,
            has_review_pending=has_review_pending,
            has_unnamed_people=has_unnamed_people,
            matched_count=len(face_filter_photo_ids),
            constrained_count=len(execution_context.constrained_photo_ids),
        )

    # ── Metadata filter (EXIF / Photo fields) ──────────────────────────────
    if execution_context.metadata_only_requested and not execution_context.metadata_only_allowed:
        logger.debug(
            "[search] metadata_only ignored due to semantic intent=%s",
            execution_context.search_query_plan.intent,
        )

    (
        concept_terms_for_debug,
        concept_entity_terms_for_debug,
        concept_facets_for_debug,
    ) = derive_concept_query_context(
        execution_context.search_query_plan
    )
    execution_context.concept_terms_for_debug = concept_terms_for_debug
    execution_context.concept_entity_terms_for_debug = concept_entity_terms_for_debug
    execution_context.concept_facets_for_debug = concept_facets_for_debug
    execution_context.concept_candidates_count = 0
    execution_context.people_visual_candidates_count = 0
    execution_context.concept_debug_info = {
        "enabled": project_id is not None,
        "reason": "service_not_connected_to_rrf_yet" if project_id is None else "connected",
        "concept_terms": concept_terms_for_debug,
        "concept_facets": concept_facets_for_debug,
        "entity_terms": concept_entity_terms_for_debug,
        "candidates": execution_context.concept_candidates_count,
        "top_scores": [],
    }

    def _build_debug_payload(**kwargs) -> dict:
        return build_logged_debug_payload(
            logger,
            SearchDebugContext(
                query_plan=execution_context.search_query_plan,
                settings=execution_context.effective_settings,
                trace=trace,
                embedding_dimension=global_settings.embedding_dimension,
                people_query_plan=execution_context.people_query_plan,
                people_candidates=execution_context.people_candidates_debug,
                people_filter_mode=execution_context.people_resolution.people_filter_mode,
                matched_person_ids=execution_context.matched_person_ids,
                metadata_filter_active=execution_context.metadata_filter_active,
                metadata_filter_skipped_reason=execution_context.metadata_filter_skipped_reason,
                metadata_only_allowed=execution_context.metadata_only_allowed,
                concept_terms=concept_terms_for_debug,
                concept_entity_terms=concept_entity_terms_for_debug,
                concept_debug=execution_context.concept_debug_info,
                concept_candidates=execution_context.concept_candidates_count,
                people_visual_candidates=execution_context.people_visual_candidates_count,
            ),
            **kwargs,
        )

    metadata_stage = run_metadata_stage(
        db,
        execution_context=execution_context,
        trace_writer=trace_writer,
    )
    execution_context.constrained_photo_ids = metadata_stage.constrained_photo_ids
    if metadata_stage.metadata_only_candidates is not None:
        logger.debug("[search] path=metadata-only filters=%s", execution_context.metadata_filters)
        total, items, debug_payload = build_result_response(
            db,
            metadata_stage.metadata_only_candidates,
            project_id=project_id or 0,
            result_mode="hybrid",
            path="metadata-only",
            page=page,
            page_size=page_size,
            debug=debug,
            trace=trace,
            debug_factory=_build_debug_payload,
            debug_kwargs={
                "mode": "metadata",
                "keyword_candidates": 0,
                "vector_candidates": 0,
                "merged_candidates": len(metadata_stage.metadata_only_candidates),
                "fallback_reason": "",
                "metadata_filters": execution_context.metadata_filters,
                "metadata_candidates": len(metadata_stage.metadata_only_candidates),
                "metadata_only": True,
            },
        )
        logger.debug(
            "[search] ── DONE ── path=metadata-only total=%d items=%d page=%d",
            total,
            len(items),
            page,
        )
        return total, items, debug_payload

    people_stage = run_people_stage(
        db,
        execution_context=execution_context,
        trace_writer=trace_writer,
    )
    execution_context.constrained_photo_ids = people_stage.constrained_photo_ids
    execution_context.people_results = people_stage.people_results
    execution_context.matched_person_ids = people_stage.matched_person_ids
    execution_context.people_candidates_debug = people_stage.people_candidates_debug
    if people_stage.people_only_candidates is not None:
        total, items, debug_payload = build_result_response(
            db,
            people_stage.people_only_candidates,
            project_id=project_id or 0,
            result_mode="hybrid",
            path="people-only",
            page=page,
            page_size=page_size,
            debug=debug,
            trace=trace,
            debug_factory=_build_debug_payload,
            debug_kwargs={
                "mode": "people",
                "keyword_candidates": 0,
                "vector_candidates": 0,
                "merged_candidates": len(people_stage.people_only_candidates),
                "fallback_reason": "",
            },
        )
        logger.debug(
            "[search] ── DONE ── path=people-only total=%d items=%d page=%d",
            total,
            len(items),
            page,
        )
        return total, items, debug_payload

    try:
        keyword_stage = run_keyword_auxiliary_stage(
            db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        keyword_results = keyword_stage.keyword_results
        merged_keyword_results = keyword_stage.merged_keyword_results
        concept_results = keyword_stage.concept_results
        people_visual_results = keyword_stage.people_visual_results
        execution_context.concept_candidates_count = keyword_stage.concept_candidates_count
        execution_context.people_visual_candidates_count = keyword_stage.people_visual_candidates_count
        execution_context.concept_debug_info = keyword_stage.concept_debug_info
    except SQLAlchemyError as exc:
        fallback_metadata_filters = execution_context.metadata_filters
        if project_id is not None and not execution_context.metadata_filter_active:
            fallback_metadata_filters = understand_query(
                query,
                project_id=project_id,
                concept_taxonomy=execution_context.effective_settings.concept_taxonomy,
            ).metadata_filters
        fallback_active = bool(
            fallback_metadata_filters.get("year")
            or fallback_metadata_filters.get("month")
            or fallback_metadata_filters.get("date_from")
            or fallback_metadata_filters.get("place_terms")
        )
        if not (fallback_active and project_id is not None):
            raise
        db.rollback()
        meta_results = MetadataRecallService(db, project_id).search(
            metadata_filters=fallback_metadata_filters,
            folder_photo_subquery=folder_photo_subquery,
        )
        total, items = build_result_items(
            db,
            meta_results,
            project_id=project_id,
            mode="hybrid",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_stage(
            "keyword_recall",
            fallback="metadata",
            error=str(exc),
            metadata_candidates=len(meta_results),
        )
        debug_payload = None
        if debug:
            debug_payload = _build_debug_payload(
                mode="metadata",
                keyword_candidates=0,
                vector_candidates=0,
                merged_candidates=len(meta_results),
                fallback_reason=str(exc),
                metadata_filters=fallback_metadata_filters,
                metadata_candidates=len(meta_results),
                metadata_only=True,
            )
        return total, items, debug_payload

    # ── Keyword-only mode ─────────────────────────────────────────────────────
    if execution_context.effective_mode == "keyword" or project_id is None:
        logger.debug("[search] path=keyword-only")
        total, items = build_result_items(
            db,
            _attach_people_explain(merged_keyword_results, execution_context.people_results),
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_result(
            path="keyword-only",
            total=total,
            items_in_page=len(items),
            page=page,
        )
        debug_payload: Optional[dict] = None
        if debug:
            debug_payload = _build_debug_payload(
                mode="keyword",
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(merged_keyword_results),
                fallback_reason="",
            )
        logger.debug(
            "[search] ── DONE ── path=keyword-only total=%d items=%d page=%d",
            total, len(items), page,
        )
        return total, items, debug_payload

    # ── Vector / hybrid path ──────────────────────────────────────────────────
    vector_stage = run_vector_stage(
        db,
        execution_context=execution_context,
        trace_writer=trace_writer,
    )
    vector_scores = vector_stage.vector_scores
    embedding_model = vector_stage.embedding_model
    fallback_reason = vector_stage.fallback_reason
    stale_embedding_filtered = vector_stage.stale_embedding_filtered
    if vector_stage.error is not None:
        exc = vector_stage.error
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
        if execution_context.effective_mode == "vector":
            trace_writer.write_result(
                path="vector-error",
                total=0,
                items_in_page=0,
                page=page,
            )
            debug_payload = None
            if debug:
                debug_payload = _build_debug_payload(
                    mode="vector",
                    embedding_model=embedding_model,
                    keyword_candidates=len(keyword_results),
                    vector_candidates=0,
                    merged_candidates=0,
                    fallback_reason=fallback_reason,
                )
            return 0, [], debug_payload
        # hybrid falls back to keyword-only
        total, items = build_result_items(
            db,
            _attach_people_explain(merged_keyword_results, execution_context.people_results),
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_result(
            path="hybrid-kw-fallback",
            total=total,
            items_in_page=len(items),
            page=page,
        )
        debug_payload = None
        if debug:
            debug_payload = _build_debug_payload(
                mode="hybrid",
                embedding_model=embedding_model,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(merged_keyword_results),
                displayed_candidates=total,
                fallback_reason=fallback_reason,
            )
        return total, items, debug_payload

    # ── Vector-only mode ──────────────────────────────────────────────────────
    if execution_context.effective_mode == "vector":
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
        vector_only = _attach_people_explain(vector_only, execution_context.people_results)
        total, items = build_result_items(
            db,
            vector_only,
            project_id=project_id or 0,
            mode="vector",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        trace_writer.write_result(
            path="vector-only",
            total=total,
            items_in_page=len(items),
            page=page,
        )
        debug_payload = None
        if debug:
            debug_payload = _build_debug_payload(
                mode="vector",
                embedding_model=embedding_model,
                keyword_candidates=len(keyword_results),
                vector_candidates=len(vector_scores),
                merged_candidates=len(vector_only),
                displayed_candidates=total,
                fallback_reason="",
            )
        return total, items, debug_payload

    # ── Hybrid: RRF merge ─────────────────────────────────────────────────────
    logger.debug(
        "[search] path=hybrid rrf_merge kw_candidates=%d vec_candidates=%d people_candidates=%d",
        len(merged_keyword_results), len(vector_scores), len(execution_context.people_results),
    )
    fusion_result = fuse_hybrid_candidates(
        merged_keyword_results,
        vector_scores,
        execution_context.effective_settings,
        concept_candidates_count=len(concept_results),
        people_results=execution_context.people_results,
        people_weight=_PEOPLE_RRF_WEIGHT,
    )
    merged = fusion_result.candidates
    logger.debug(
        "[search] rrf_merge done merged=%d top_final_scores=%s",
        len(merged),
        [round(c.final_score, 6) for c in merged[:5]],
    )
    trace_writer.write(fusion_result.trace_event)

    post_fusion = apply_post_fusion_pipeline(
        db,
        merged,
        query_plan=execution_context.search_query_plan,
        settings=execution_context.effective_settings,
        project_id=project_id,
    )
    merged = post_fusion.candidates
    filtered_out = post_fusion.filtered_out
    filtered_count = post_fusion.filtered_count
    trace_writer.extend(post_fusion.trace_events)

    total, items = build_result_items(
        db,
        merged,
        project_id=project_id or 0,
        mode="hybrid",
        page=page,
        page_size=page_size,
        debug=debug,
    )
    trace_writer.write_result(
        path="hybrid",
        total=total,
        items_in_page=len(items),
        page=page,
    )
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
        debug_payload = _build_debug_payload(
            mode="hybrid",
            embedding_model=embedding_model,
            keyword_candidates=len(keyword_results),
            vector_candidates=len(vector_scores),
            merged_candidates=len(merged),
            fallback_reason="",
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
