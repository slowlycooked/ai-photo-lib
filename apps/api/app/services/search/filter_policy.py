"""Search filter policies and evidence-level filtering utilities."""
from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...models.ai import PhotoAIAnalysis
from ...models.face import FaceDetection, Person, PersonFaceAssignment
from ...models.photo import Photo
from ...services.folder_service import build_folder_photo_ids_subquery
from .query_understanding import SearchQueryPlan
from .types import (
    EVIDENCE_SCORE_MAP,
    EffectiveSearchSettings,
    SearchCandidate,
)

# Normal vector threshold for support-assisted C (below vector_strict_score)
_VECTOR_NORMAL_THRESHOLD = 0.32

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

_DEFAULT_INDOOR_QUERY_TRIGGERS: frozenset[str] = frozenset({
    "室内",
    "室内空间",
    "indoor",
    "indoors",
    "interior",
})

_DEFAULT_INDOOR_POSITIVE_TERMS: frozenset[str] = frozenset({
    "室内",
    "屋内",
    "室内场景",
    "房间",
    "客厅",
    "卧室",
    "厨房",
    "indoor",
    "interior",
})

_DEFAULT_INDOOR_NEGATIVE_TERMS: frozenset[str] = frozenset({
    "户外",
    "室外",
    "自然",
    "风景",
    "outdoor",
    "outside",
    "landscape",
    "exterior",
})

_DEFAULT_ANIMAL_GENERIC_TERMS: frozenset[str] = frozenset({
    "动物",
    "宠物",
    "野生动物",
    "动物园",
    "小动物",
    "animal",
    "animals",
})

_DEFAULT_ANIMAL_WEAK_SCENE_TERMS: frozenset[str] = frozenset({
    "动物园",
    "宠物店",
})

def _core_terms_for_domain(
    query_plan: SearchQueryPlan,
    domain: str,
) -> tuple[frozenset[str], frozenset[str]]:
    evidence = getattr(query_plan, "core_facet_evidence", None) or {}
    domain_payload = evidence.get(domain) or {}

    positive_terms = frozenset(
        str(term).lower().strip()
        for term in (domain_payload.get("positive_terms") or [])
        if str(term).strip()
    )
    negative_terms = frozenset(
        str(term).lower().strip()
        for term in (domain_payload.get("negative_terms") or [])
        if str(term).strip()
    )

    return positive_terms, negative_terms


def _animal_evidence_payload(query_plan: SearchQueryPlan) -> dict:
    evidence = getattr(query_plan, "core_facet_evidence", None) or {}
    payload = evidence.get("animal")
    return payload if isinstance(payload, dict) else {}


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


_STRUCTURED_FILTER_FIELDS = {
    "people_count": PhotoAIAnalysis.people_count,
    "taken_at": Photo.taken_at,
    "created_at": Photo.created_at,
    "camera_make": Photo.camera_make,
    "camera_model": Photo.camera_model,
    "iso": Photo.iso,
}


def _apply_structured_operator(query, expression, operator: str, value):
    if operator == "eq":
        return query.filter(expression == value)
    if operator == "ne":
        return query.filter(expression != value)
    if operator == "gt":
        return query.filter(expression > value)
    if operator == "gte":
        return query.filter(expression >= value)
    if operator == "lt":
        return query.filter(expression < value)
    if operator == "lte":
        return query.filter(expression <= value)
    if operator == "contains":
        return query.filter(expression.ilike(f"%{value}%"))
    if operator == "in" and isinstance(value, list):
        return query.filter(expression.in_(value))
    return query


def resolve_structured_filter_photo_ids(
    db: Session,
    *,
    project_id: int,
    filter_clauses: list[dict],
    folder_photo_subquery: Optional[Select] = None,
) -> set[int]:
    """Resolve validated dynamic filter clauses through an allow-listed registry."""
    query = (
        db.query(Photo.id)
        .outerjoin(
            PhotoAIAnalysis,
            (PhotoAIAnalysis.photo_id == Photo.id)
            & (PhotoAIAnalysis.project_id == Photo.project_id),
        )
        .filter(Photo.project_id == project_id, Photo.deleted_at.is_(None))
    )

    for clause in filter_clauses:
        field = str(clause.get("field") or "")
        operator = str(clause.get("operator") or "")
        value = clause.get("value")
        if field == "has_gps" and operator in {"eq", "ne"} and isinstance(value, bool):
            has_gps = value if operator == "eq" else not value
            gps_condition = sa.and_(
                Photo.gps_latitude.is_not(None),
                Photo.gps_longitude.is_not(None),
            )
            query = query.filter(gps_condition if has_gps else sa.not_(gps_condition))
            continue

        expression = _STRUCTURED_FILTER_FIELDS.get(field)
        if expression is None:
            continue
        query = _apply_structured_operator(query, expression, operator, value)

    if folder_photo_subquery is not None:
        query = query.filter(Photo.id.in_(folder_photo_subquery))

    return {int(row[0]) for row in query.all()}


def is_explicit_indoor_query(query_plan: SearchQueryPlan) -> bool:
    exact_lower = {t.lower() for t in query_plan.exact_terms}
    matched_lower = {t.lower() for t in query_plan.matched_keys}
    core_facet_evidence = getattr(query_plan, "core_facet_evidence", None) or {}
    indoor_payload = core_facet_evidence.get("indoor") or {}
    indoor_query_triggers = {
        str(term).lower().strip()
        for term in (indoor_payload.get("query_triggers") or [])
        if str(term).strip()
    }
    if not indoor_query_triggers:
        indoor_query_triggers = _DEFAULT_INDOOR_QUERY_TRIGGERS
    return (
        query_plan.filters.get("indoor_outdoor") == "indoor"
        and "scene" in query_plan.core_facets
        and bool(indoor_query_triggers & (exact_lower | matched_lower))
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

    animal_payload = _animal_evidence_payload(query_plan)
    animal_generic_terms = frozenset(
        str(term).lower().strip()
        for term in (animal_payload.get("generic_terms") or [])
        if str(term).strip()
    )
    if not animal_generic_terms:
        animal_generic_terms = _DEFAULT_ANIMAL_GENERIC_TERMS
    animal_entity_hints = frozenset(
        str(term).lower().strip()
        for term in (animal_payload.get("entity_hints") or [])
        if str(term).strip()
    )
    animal_weak_scene_terms = frozenset(
        str(term).lower().strip()
        for term in (animal_payload.get("weak_scene_terms") or [])
        if str(term).strip()
    )
    if not animal_weak_scene_terms:
        animal_weak_scene_terms = _DEFAULT_ANIMAL_WEAK_SCENE_TERMS

    entity_terms = [
        term.lower()
        for term in (query_plan.exact_terms + query_plan.expanded_terms)
        if term.lower() not in animal_generic_terms
    ]
    positive_terms = entity_terms or list(animal_entity_hints)

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

    weak_scene_only = any(term in weak_text for term in animal_weak_scene_terms) and not has_positive

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

    indoor_positive_terms, indoor_negative_terms = _core_terms_for_domain(query_plan, "indoor")
    if not indoor_positive_terms:
        indoor_positive_terms = _DEFAULT_INDOOR_POSITIVE_TERMS
    if not indoor_negative_terms:
        indoor_negative_terms = _DEFAULT_INDOOR_NEGATIVE_TERMS

    has_positive = any(term in rich_text for term in indoor_positive_terms)
    has_negative = any(term in combined_text for term in indoor_negative_terms)
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

    if getattr(query_plan, "intent", "") == "animal_search":
        return animal_core_facet_passes(candidate, ai_analysis, query_plan, settings)

    core_facets = query_plan.core_facets
    if "time" not in core_facets and "lighting" not in core_facets:
        return True, ""

    positive_terms, negative_terms = _core_terms_for_domain(query_plan, "night")
    if not positive_terms and not negative_terms:
        core_facet_evidence = query_plan.core_facet_evidence or {}
        positive_terms = frozenset(
            str(term).lower().strip()
            for term in (core_facet_evidence.get("positive_terms") or [])
            if str(term).strip()
        )
        negative_terms = frozenset(
            str(term).lower().strip()
            for term in (core_facet_evidence.get("negative_terms") or [])
            if str(term).strip()
        )
    if not positive_terms and not negative_terms:
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

    has_positive = any(term in combined_text for term in positive_terms)
    has_negative = any(term in combined_text for term in negative_terms)

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
