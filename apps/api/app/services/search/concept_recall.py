"""ConceptRecallService — recall by normalized semantic concepts."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from ...services.query_understanding_service import SearchQueryPlan
from ...services.concept_normalizer import normalize_concepts_from_payload
from .types import EffectiveSearchSettings, SearchCandidate

logger = logging.getLogger(__name__)

_ANIMAL_CONCEPT_TERMS: set[str] = {
    "动物",
    "宠物",
    "小动物",
    "野生动物",
    "水生动物",
    "昆虫",
}

_ANIMAL_GENERIC_TERMS: set[str] = {
    "动物",
    "宠物",
    "小动物",
    "野生动物",
    "水生动物",
    "animal",
}

_PEOPLE_CONCEPT_TERMS: list[str] = [
    "人物",
    "单人照",
    "人像",
    "多人",
    "合照",
    "合影",
    "集体照",
    "自拍",
    "全家福",
]

_PEOPLE_FACETS: list[str] = ["people", "group_photo"]


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


def derive_concept_query_terms(query_plan: SearchQueryPlan) -> tuple[list[str], list[str]]:
    concept_terms, entity_terms, _concept_facets = derive_concept_query_context(query_plan)
    return concept_terms, entity_terms


def derive_concept_query_context(
    query_plan: SearchQueryPlan,
) -> tuple[list[str], list[str], list[str]]:
    concept_terms: list[str] = []
    entity_terms: list[str] = []
    concept_facets: list[str] = []

    if query_plan.intent == "animal_search":
        for term in query_plan.exact_terms + query_plan.broad_terms + query_plan.concept_terms:
            text = str(term).strip()
            if not text:
                continue
            if text in _ANIMAL_CONCEPT_TERMS:
                concept_terms.append(text)

        for term in query_plan.exact_terms + query_plan.expanded_terms:
            text = str(term).strip()
            if not text or text in _ANIMAL_GENERIC_TERMS:
                continue
            normalized = normalize_concepts_from_payload(object_tags=[text]).semantic_entities
            if normalized:
                entity_terms.extend(normalized)
            else:
                entity_terms.append(text)
    else:
        concept_terms.extend([str(t).strip() for t in query_plan.concept_terms if str(t).strip()])

    if query_plan.intent in ("people_search", "group_photo_search"):
        if "人物" not in concept_terms:
            concept_terms.append("人物")
        for term in query_plan.exact_terms + query_plan.expanded_terms + query_plan.broad_terms:
            text = str(term).strip()
            if text in _PEOPLE_CONCEPT_TERMS and text not in concept_terms:
                concept_terms.append(text)
        for text in _PEOPLE_CONCEPT_TERMS:
            if text in query_plan.original_query and text not in concept_terms:
                concept_terms.append(text)
        concept_facets.extend(["people"])
        if any(term in concept_terms for term in ("多人", "合照", "合影", "集体照", "全家福")):
            concept_facets.append("group_photo")

    if "group_photo" in query_plan.core_facets and "group_photo" not in concept_facets:
        concept_facets.append("group_photo")
    if "people" in query_plan.core_facets and "people" not in concept_facets:
        concept_facets.append("people")

    return (
        _dedupe_preserve_order(concept_terms),
        _dedupe_preserve_order(entity_terms),
        _dedupe_preserve_order(concept_facets),
    )


def _concept_filter(concepts: list[str]):
    clauses = [PhotoAIAnalysis.semantic_concepts.any(term) for term in concepts]
    return or_(*clauses)


def _entity_filter(entities: list[str]):
    clauses = [
        PhotoAIAnalysis.object_tags.any(term)
        for term in entities
    ] + [
        PhotoAIAnalysis.search_keywords.any(term)
        for term in entities
    ]
    return or_(*clauses)


def _facet_match_from_raw(raw_result: object, facets: list[str]) -> list[str]:
    if not facets:
        return []
    semantic_facets = _extract_semantic_list(raw_result, "facets")
    return [facet for facet in facets if facet in semantic_facets]


def _coverage_score(hits: list[str], terms: list[str]) -> float:
    if not terms:
        return 0.0
    return min(1.0, len(hits) / len(terms))


def _score_from_hits(
    concept_hits: list[str],
    entity_hits: list[str],
    *,
    concept_terms: list[str],
    entity_terms: list[str],
) -> float:
    """Compute concept recall score from term coverage.

    Stage-1 keeps concept recall self-contained and avoids introducing
    new configurable fusion weights in business logic.
    """
    concept_coverage = _coverage_score(concept_hits, concept_terms)
    entity_coverage = _coverage_score(entity_hits, entity_terms)

    if concept_terms and entity_terms:
        return round((concept_coverage + entity_coverage) / 2.0, 6)
    if concept_terms:
        return round(concept_coverage, 6)
    if entity_terms:
        return round(entity_coverage, 6)
    return 0.0


class ConceptRecallService:
    """Recall photos by concept fields such as semantic_concepts."""

    def __init__(self, db: Session, search_settings: EffectiveSearchSettings) -> None:
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
        concept_terms, entity_terms, concept_facets = derive_concept_query_context(query_plan)
        if not concept_terms and not entity_terms and not concept_facets:
            return []

        top_k = limit if limit is not None else self._settings.keyword_top_k

        base_query = (
            self._db.query(PhotoAIAnalysis)
            .join(Photo, Photo.id == PhotoAIAnalysis.photo_id)
            .filter(Photo.deleted_at.is_(None))
            .filter(Photo.project_id == project_id, PhotoAIAnalysis.project_id == project_id)
        )

        term_filters = []
        if concept_terms:
            term_filters.append(_concept_filter(concept_terms))
        if entity_terms:
            term_filters.append(_entity_filter(entity_terms))
        if term_filters:
            base_query = base_query.filter(or_(*term_filters))

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
            concepts_from_column = [str(v).strip() for v in (ai.semantic_concepts or []) if str(v).strip()]
            concepts_from_raw = _extract_semantic_list(ai.raw_result, "concepts")
            entities_from_raw = _extract_semantic_list(ai.raw_result, "entities")
            entity_hint_fields = [
                str(v).strip() for v in (ai.object_tags or []) if str(v).strip()
            ] + [
                str(v).strip() for v in (ai.search_keywords or []) if str(v).strip()
            ]

            concept_space = set(concepts_from_column + concepts_from_raw)
            entity_space = set(entities_from_raw + entity_hint_fields)

            concept_hits = [term for term in concept_terms if term in concept_space]
            entity_hits = [term for term in entity_terms if term in entity_space]
            facet_hits = _facet_match_from_raw(ai.raw_result, concept_facets)
            if not concept_hits and not entity_hits and not facet_hits:
                continue

            score = _score_from_hits(
                concept_hits,
                entity_hits,
                concept_terms=concept_terms,
                entity_terms=entity_terms,
            )
            matched = _dedupe_preserve_order(concept_hits + entity_hits + facet_hits)

            # ── Entity evidence enforcement for animal_search ──────────────
            # When a specific entity is expected (entity_terms is non-empty) but this
            # photo only matched a broad concept ("动物") without any entity evidence,
            # the match is too weak.  Downgrade hit_tiers so the evidence filter
            # (min_display_evidence_level) can suppress these spurious results.
            is_pure_concept_only_animal = (
                query_plan.intent == "animal_search"
                and entity_terms  # specific animal entities are expected
                and not entity_hits  # this photo has no matching entity evidence
                and concept_hits  # it only passed the broad concept filter
            )
            if is_pure_concept_only_animal:
                effective_score = round(score * 0.3, 6)
                candidates.append(
                    SearchCandidate(
                        photo_id=ai.photo_id,
                        keyword_score=effective_score,
                        matched_tags=matched,
                        match_source=["concept"],
                        field_scores={"concept": effective_score},
                        keyword_explain={
                            "semantic_concepts": concept_hits,
                            "semantic_entities": entity_hits,
                            "semantic_facets": facet_hits,
                            "concept_only_downgraded": True,
                            "concept_term_coverage": round(
                                _coverage_score(concept_hits, concept_terms),
                                6,
                            ),
                            "entity_term_coverage": 0.0,
                        },
                        hit_tiers={"weak"},
                        term_level_hits={
                            "exact": [],
                            "strong": [],
                            "support": [],
                            "weak": matched,
                            "negative": [],
                        },
                    )
                )
                continue

            candidates.append(
                SearchCandidate(
                    photo_id=ai.photo_id,
                    keyword_score=score,
                    matched_tags=matched,
                    match_source=["concept"],
                    field_scores={"concept": round(score, 6)},
                    keyword_explain={
                        "semantic_concepts": concept_hits,
                        "semantic_entities": entity_hits,
                        "semantic_facets": facet_hits,
                        "concept_term_coverage": round(
                            _coverage_score(concept_hits, concept_terms),
                            6,
                        ),
                        "entity_term_coverage": round(
                            _coverage_score(entity_hits, entity_terms),
                            6,
                        ),
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
            "[concept_recall] project_id=%d concepts=%s entities=%s candidates=%d",
            project_id,
            concept_terms,
            entity_terms,
            len(candidates),
        )
        return candidates
