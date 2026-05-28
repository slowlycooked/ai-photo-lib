"""Search filter policies and evidence-level filtering utilities."""
from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...models.ai import PhotoAIAnalysis
from ...models.face import FaceDetection, Person, PersonFaceAssignment
from ...services.folder_service import build_folder_photo_ids_subquery
from .query_understanding import SearchQueryPlan
from .types import (
    EVIDENCE_SCORE_MAP,
    EffectiveSearchSettings,
    SearchCandidate,
)

# Normal vector threshold for support-assisted C (below vector_strict_score)
_VECTOR_NORMAL_THRESHOLD = 0.32

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


def resolve_folder_photo_subquery(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[Select]:
    return build_folder_photo_ids_subquery(db, project_id, folder_id, folder_scope)


def resolve_face_filter_photo_ids(
    db: Session,
    *,
    project_id: int,
    face_count_min: Optional[int],
    face_count_max: Optional[int],
    has_review_pending: Optional[bool],
    has_unnamed_people: Optional[bool],
) -> set[int]:
    counts = (
        db.query(FaceDetection.photo_id, func.count(FaceDetection.id).label("face_count"))
        .filter(
            FaceDetection.project_id == project_id,
            FaceDetection.status != "failed",
        )
        .group_by(FaceDetection.photo_id)
        .all()
    )
    photo_ids = {int(photo_id) for photo_id, _ in counts}
    if face_count_min is not None or face_count_max is not None:
        filtered_by_count: set[int] = set()
        for photo_id, count in counts:
            count_int = int(count)
            if face_count_min is not None and count_int < face_count_min:
                continue
            if face_count_max is not None and count_int > face_count_max:
                continue
            filtered_by_count.add(int(photo_id))
        photo_ids = filtered_by_count

    if has_review_pending is not None:
        review_photo_ids = {
            int(row[0])
            for row in (
                db.query(FaceDetection.photo_id)
                .join(
                    PersonFaceAssignment,
                    sa.and_(
                        PersonFaceAssignment.project_id == FaceDetection.project_id,
                        PersonFaceAssignment.face_detection_id == FaceDetection.id,
                    ),
                )
                .filter(
                    FaceDetection.project_id == project_id,
                    PersonFaceAssignment.assignment_status == "review_pending",
                )
                .distinct()
                .all()
            )
        }
        photo_ids = photo_ids & review_photo_ids if has_review_pending else photo_ids - review_photo_ids

    if has_unnamed_people is not None:
        unnamed_photo_ids = {
            int(row[0])
            for row in (
                db.query(FaceDetection.photo_id)
                .join(
                    PersonFaceAssignment,
                    sa.and_(
                        PersonFaceAssignment.project_id == FaceDetection.project_id,
                        PersonFaceAssignment.face_detection_id == FaceDetection.id,
                        PersonFaceAssignment.assignment_status != "rejected",
                    ),
                )
                .join(
                    Person,
                    sa.and_(
                        Person.project_id == PersonFaceAssignment.project_id,
                        Person.id == PersonFaceAssignment.person_id,
                    ),
                )
                .filter(
                    FaceDetection.project_id == project_id,
                    Person.is_named.is_(False),
                )
                .distinct()
                .all()
            )
        }
        photo_ids = photo_ids & unnamed_photo_ids if has_unnamed_people else photo_ids - unnamed_photo_ids

    return photo_ids


def is_explicit_indoor_query(query_plan: SearchQueryPlan) -> bool:
    exact_lower = {t.lower() for t in query_plan.exact_terms}
    matched_lower = {t.lower() for t in query_plan.matched_keys}
    return (
        query_plan.filters.get("indoor_outdoor") == "indoor"
        and "scene" in query_plan.core_facets
        and bool({"室内", "indoor", "indoors"} & (exact_lower | matched_lower))
    )


def animal_core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional[PhotoAIAnalysis],
    query_plan: SearchQueryPlan,
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

    entity_tag_set: set[str] = set()
    for field_name in ("object_tags", "search_keywords"):
        tags = getattr(ai_analysis, field_name, None) or []
        entity_tag_set.update(t.lower().strip() for t in tags if str(t).strip())

    raw_result = getattr(ai_analysis, "raw_result", None)
    if isinstance(raw_result, dict):
        for item in (raw_result.get("animals") or []):
            val = str(item).lower().strip()
            if val:
                entity_tag_set.add(val)

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


def indoor_core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional[PhotoAIAnalysis],
    query_plan: SearchQueryPlan,
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


def core_facet_passes(
    candidate: SearchCandidate,
    ai_analysis: Optional[PhotoAIAnalysis],
    query_plan: SearchQueryPlan,
    settings: EffectiveSearchSettings,
) -> tuple[bool, str]:
    """Check if a candidate satisfies core-facet evidence requirements."""
    if is_explicit_indoor_query(query_plan):
        return indoor_core_facet_passes(candidate, ai_analysis, query_plan, settings)

    if query_plan.intent == "animal_search":
        return animal_core_facet_passes(candidate, ai_analysis, query_plan, settings)

    core_facets = query_plan.core_facets
    if "time" not in core_facets and "lighting" not in core_facets:
        return True, ""

    is_night_query = any(
        k in {"夜景", "夜晚", "晚上", "黑夜", "夜间", "夜色"}
        for k in query_plan.matched_keys
    )
    if not is_night_query:
        return True, ""

    require_core = getattr(settings, "require_core_facet_match", False)
    allow_vector_only = getattr(settings, "allow_vector_only_for_facet_query", True)

    if ai_analysis is None:
        if allow_vector_only and candidate.vector_score >= settings.vector_strict_score:
            return True, "vector_only_high_confidence"
        return False if require_core else True, "no_ai_analysis"

    all_text: list[str] = []
    for field_name in ("caption", "ocr_text"):
        value = getattr(ai_analysis, field_name, None) or ""
        if value:
            all_text.append(value.lower())
    for field_name in (
        "scene_tags",
        "object_tags",
        "activity_tags",
        "search_keywords",
        "location_clues",
    ):
        tags = getattr(ai_analysis, field_name, None) or []
        all_text.extend(tag.lower() for tag in tags)
    combined_text = " ".join(all_text)

    has_positive = any(term in combined_text for term in _NIGHT_CORE_POSITIVE)
    has_negative = any(term in combined_text for term in _NIGHT_CORE_NEGATIVE)

    if allow_vector_only and candidate.vector_score >= settings.vector_strict_score:
        if has_negative and not has_positive:
            return False, f"night_negative_evidence={has_negative}"
        return True, "vector_high_confidence"

    if has_positive and not has_negative:
        return True, "night_positive_evidence"
    if has_positive and has_negative:
        if candidate.evidence_level in ("A", "B"):
            return True, "night_conflicting_but_strong_keyword"
        return False, "night_conflicting_evidence"
    if not has_positive:
        if require_core:
            return False, "night_no_positive_evidence"
        if candidate.evidence_level in ("A", "B"):
            return True, "night_no_evidence_but_strong_keyword"
        return False, "night_no_core_facet_evidence"

    return True, ""


def compute_evidence_level(
    candidate: SearchCandidate,
    settings: Optional[EffectiveSearchSettings] = None,
) -> str:
    """Classify a merged candidate into evidence level A-F."""
    hit_tiers = candidate.hit_tiers
    vector_strict = settings.vector_strict_score if settings else 0.42
    vector_normal = _VECTOR_NORMAL_THRESHOLD

    if "exact" in hit_tiers:
        return "A"
    if "strong" in hit_tiers:
        return "B"
    if "negative" in hit_tiers and candidate.vector_score < vector_normal:
        return "F"
    if candidate.vector_score >= vector_strict:
        return "C"
    if "support" in hit_tiers and candidate.vector_score >= vector_normal:
        return "C"
    if "support" in hit_tiers or "weak" in hit_tiers:
        return "D"
    if candidate.vector_score >= 0.25:
        return "D"
    if candidate.vector_score > 0:
        return "E"
    return "E"


def apply_evidence_scoring(
    candidates: list[SearchCandidate],
    settings: EffectiveSearchSettings,
) -> list[SearchCandidate]:
    """Apply evidence-level bonus/penalty to final scores."""
    for candidate in candidates:
        level = candidate.evidence_level or "E"
        ev_score = EVIDENCE_SCORE_MAP.get(level, 0.0)
        bonus = ev_score * settings.evidence_weight

        neg_penalty = 0.0
        if settings.enable_negative_penalty and "negative" in candidate.hit_tiers:
            neg_hits = len(candidate.term_level_hits.get("negative", []))
            neg_penalty = neg_hits * settings.negative_term_penalty

        old_score = candidate.final_score
        candidate.final_score = max(0.0, old_score + bonus - neg_penalty)
        candidate.score_breakdown = {
            "rrf_score": round(candidate.rrf_score, 6),
            "pre_evidence_final": round(old_score, 6),
            "evidence_level": level,
            "evidence_bonus": round(bonus, 6),
            "negative_penalty": round(neg_penalty, 6),
            "final_score": round(candidate.final_score, 6),
        }

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    return candidates


def apply_semantic_tag_boost(
    db: Session,
    candidates: list[SearchCandidate],
    query_plan: SearchQueryPlan,
    project_id: int,
) -> list[SearchCandidate]:
    """Post-RRF score adjustment using direct tag matching."""
    if not candidates:
        return candidates

    photo_ids = [candidate.photo_id for candidate in candidates]
    rows = (
        db.query(PhotoAIAnalysis)
        .filter(
            PhotoAIAnalysis.photo_id.in_(photo_ids),
            PhotoAIAnalysis.project_id == project_id,
        )
        .all()
    )
    ai_by_id: dict[int, PhotoAIAnalysis] = {row.photo_id: row for row in rows}

    expanded_lower = {term.lower() for term in query_plan.expanded_terms}
    support_lower = {term.lower() for term in query_plan.support_terms}
    broad_lower = {term.lower() for term in query_plan.broad_terms}
    penalize_lower = {term.lower() for term in query_plan.penalize_tags}

    tag_fields = ("scene_tags", "object_tags", "activity_tags", "search_keywords")

    for candidate in candidates:
        ai = ai_by_id.get(candidate.photo_id)
        if ai is None:
            continue

        all_tags_lower: list[str] = []
        for field_name in tag_fields:
            tags = getattr(ai, field_name, None) or []
            all_tags_lower.extend(tag.lower() for tag in tags)

        boost = 0.0
        for tag in all_tags_lower:
            if any(expanded in tag for expanded in expanded_lower):
                boost += 0.04
            elif any(support in tag for support in support_lower):
                boost += 0.02
            elif any(broad in tag for broad in broad_lower):
                boost += 0.01
            if penalize_lower and any(penalize in tag for penalize in penalize_lower):
                boost -= 0.03

        if boost != 0.0:
            candidate.final_score = max(0.0, candidate.final_score + boost)

    candidates.sort(key=lambda c: c.final_score, reverse=True)
    return candidates
