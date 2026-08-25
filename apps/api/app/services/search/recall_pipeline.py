"""Explicit recall pipeline stages for search orchestration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..embedding_client import EmbeddingRequestError
from .concept_recall import ConceptRecallService
from .execution_context import SearchExecutionContext
from .keyword_recall import KeywordRecallService
from .metadata_recall import MetadataRecallService
from .people_recall import PeopleRecallService
from .people_visual_recall import PeopleVisualRecallService
from .recall import recall_auxiliary_candidates
from .trace_writer import SearchDebugTraceWriter, compact_filter_dict
from .types import SearchCandidate, VectorMatchScores
from .vector_recall import VectorRecallService

logger = logging.getLogger(__name__)


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))


@dataclass(frozen=True)
class MetadataStageResult:
    constrained_photo_ids: Optional[set[int]]
    metadata_only_candidates: Optional[list[SearchCandidate]]


@dataclass(frozen=True)
class PeopleStageResult:
    constrained_photo_ids: Optional[set[int]]
    people_results: list[SearchCandidate]
    matched_person_ids: list[int]
    people_candidates_debug: list[dict]
    people_only_candidates: Optional[list[SearchCandidate]]


@dataclass(frozen=True)
class KeywordAuxiliaryStageResult:
    keyword_results: list[SearchCandidate]
    merged_keyword_results: list[SearchCandidate]
    concept_results: list[SearchCandidate]
    people_visual_results: list[SearchCandidate]
    concept_candidates_count: int
    people_visual_candidates_count: int
    concept_debug_info: dict


@dataclass(frozen=True)
class VectorStageResult:
    vector_scores: dict[int, VectorMatchScores]
    embedding_model: str
    fallback_reason: str
    stale_embedding_filtered: int
    error: Optional[Exception] = None


def merge_keyword_with_aux_candidates(
    keyword_results: list[SearchCandidate],
    aux_results: list[SearchCandidate],
    *,
    aux_source: str,
) -> list[SearchCandidate]:
    """Merge auxiliary recall candidates into keyword candidates by photo_id."""
    if not aux_results:
        return keyword_results

    merged_by_photo: dict[int, SearchCandidate] = {candidate.photo_id: candidate for candidate in keyword_results}

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
            if not isinstance(current, list):
                current = [] if current is None else [current]
                existing.keyword_explain[field_name] = current

            if values is None:
                continue
            if isinstance(values, (list, tuple, set)):
                iter_values = values
            else:
                iter_values = [values]

            for value in iter_values:
                if value not in current:
                    current.append(value)

        for tier, terms in aux.term_level_hits.items():
            current = existing.term_level_hits.setdefault(tier, [])
            for term in terms:
                if term not in current:
                    current.append(term)

    return sorted(merged_by_photo.values(), key=lambda candidate: candidate.keyword_score, reverse=True)


def run_metadata_stage(
    db: Session,
    *,
    execution_context: SearchExecutionContext,
    trace_writer: SearchDebugTraceWriter,
) -> MetadataStageResult:
    """Run metadata stage and update constrained candidates."""
    started_at = perf_counter()
    if (not execution_context.metadata_filter_active) or execution_context.project_id is None:
        trace_writer.write_stage(
            "metadata_filter",
            skipped=True,
            skip_reason=(
                "project_id_missing"
                if execution_context.project_id is None
                else "metadata_filter_inactive"
            ),
            matched_count=0,
            constrained_count=len(execution_context.constrained_photo_ids or set()),
            duration_ms=_elapsed_ms(started_at),
        )
        return MetadataStageResult(
            constrained_photo_ids=execution_context.constrained_photo_ids,
            metadata_only_candidates=None,
        )

    metadata_service = MetadataRecallService(db, execution_context.project_id)
    if (
        execution_context.metadata_only_requested
        and execution_context.metadata_only_allowed
        and not execution_context.people_resolution.has_people_constraint
    ):
        metadata_results = metadata_service.search(
            metadata_filters=execution_context.metadata_filters,
            folder_photo_subquery=execution_context.folder_photo_subquery,
        )
        if execution_context.constrained_photo_ids is not None:
            metadata_results = [
                candidate
                for candidate in metadata_results
                if candidate.photo_id in execution_context.constrained_photo_ids
            ]
        trace_writer.write_stage(
            "metadata_filter",
            path="metadata-only",
            filters=compact_filter_dict(execution_context.metadata_filters),
            matched_count=len(metadata_results),
            duration_ms=_elapsed_ms(started_at),
        )
        return MetadataStageResult(
            constrained_photo_ids=execution_context.constrained_photo_ids,
            metadata_only_candidates=metadata_results,
        )

    metadata_ids = metadata_service.resolve_photo_ids(
        metadata_filters=execution_context.metadata_filters,
        folder_photo_subquery=execution_context.folder_photo_subquery,
    )
    next_constrained = (
        set(metadata_ids)
        if execution_context.constrained_photo_ids is None
        else execution_context.constrained_photo_ids & metadata_ids
    )
    logger.debug(
        "[search] metadata_filter (mixed) matched=%d constrained=%d",
        len(metadata_ids),
        len(next_constrained),
    )
    trace_writer.write_stage(
        "metadata_filter",
        path="mixed",
        filters=compact_filter_dict(execution_context.metadata_filters),
        matched_count=len(metadata_ids),
        constrained_count=len(next_constrained),
        duration_ms=_elapsed_ms(started_at),
    )
    return MetadataStageResult(
        constrained_photo_ids=next_constrained,
        metadata_only_candidates=None,
    )


def run_people_stage(
    db: Session,
    *,
    execution_context: SearchExecutionContext,
    trace_writer: SearchDebugTraceWriter,
) -> PeopleStageResult:
    """Run people recall stage and update constrained candidates."""
    started_at = perf_counter()
    if execution_context.project_id is None or not execution_context.people_resolution.has_people_constraint:
        trace_writer.write_stage(
            "people_recall",
            skipped=True,
            skip_reason=(
                "project_id_missing"
                if execution_context.project_id is None
                else "people_constraint_inactive"
            ),
            people_candidates=0,
            constrained_photo_ids=len(execution_context.constrained_photo_ids or set()),
            duration_ms=_elapsed_ms(started_at),
        )
        return PeopleStageResult(
            constrained_photo_ids=execution_context.constrained_photo_ids,
            people_results=[],
            matched_person_ids=[],
            people_candidates_debug=[],
            people_only_candidates=None,
        )

    if execution_context.people_resolution.unresolved_people:
        trace_writer.write_stage(
            "people_recall",
            people_filter_mode=execution_context.people_resolution.people_filter_mode,
            matched_person_ids=[],
            unresolved_people=execution_context.people_resolution.unresolved_people,
            people_candidates=0,
            constrained_photo_ids=0,
            duration_ms=_elapsed_ms(started_at),
        )
        return PeopleStageResult(
            constrained_photo_ids=set(),
            people_results=[],
            matched_person_ids=[],
            people_candidates_debug=[],
            people_only_candidates=(
                [] if execution_context.people_resolution.is_people_only else None
            ),
        )

    next_constrained = execution_context.constrained_photo_ids
    if next_constrained is None and execution_context.folder_photo_subquery is not None:
        folder_subquery = execution_context.folder_photo_subquery.subquery()
        folder_rows = db.query(folder_subquery.c.id).all()
        next_constrained = {int(row[0]) for row in folder_rows}

    people_filter_mode = str(execution_context.people_resolution.people_filter_mode or "none")
    people_recall = PeopleRecallService(db, execution_context.project_id).recall(
        resolution=execution_context.people_resolution,
        constrained_photo_ids=next_constrained,
    )
    people_results = people_recall.candidates
    matched_person_ids = people_recall.matched_person_ids

    people_photo_ids = people_recall.photo_ids
    if people_filter_mode != "boost":
        if next_constrained is None:
            next_constrained = set(people_photo_ids)
        else:
            next_constrained = next_constrained & set(people_photo_ids)

    people_candidates_debug = [
        {
            "photo_id": candidate.photo_id,
            "people_score": round(candidate.people_score, 6),
            "people_rank": candidate.people_rank,
            "matched_people": list(candidate.people_explain.get("matched_people", [])),
        }
        for candidate in people_results[:20]
    ]

    trace_writer.write_stage(
        "people_recall",
        people_filter_mode=people_filter_mode,
        matched_person_ids=matched_person_ids,
        people_candidates=len(people_results),
        constrained_photo_ids=len(next_constrained or set()),
        duration_ms=_elapsed_ms(started_at),
    )

    logger.debug(
        "[search] people_recall mode=%s matched_person_ids=%s candidates=%d constrained=%d",
        people_filter_mode,
        matched_person_ids,
        len(people_results),
        len(next_constrained or set()),
    )

    return PeopleStageResult(
        constrained_photo_ids=next_constrained,
        people_results=people_results,
        matched_person_ids=matched_person_ids,
        people_candidates_debug=people_candidates_debug,
        people_only_candidates=people_results if execution_context.people_resolution.is_people_only else None,
    )


def run_keyword_auxiliary_stage(
    db: Session,
    *,
    execution_context: SearchExecutionContext,
    trace_writer: SearchDebugTraceWriter,
) -> KeywordAuxiliaryStageResult:
    """Run keyword recall and auxiliary (concept/people_visual) stages."""
    started_at = perf_counter()
    keyword_service = KeywordRecallService(db, execution_context.effective_settings)
    keyword_results = keyword_service.search(
        execution_context.search_query_plan,
        project_id=execution_context.project_id or 0,
        folder_photo_subquery=execution_context.folder_photo_subquery,
        constrained_photo_ids=execution_context.constrained_photo_ids,
    )

    auxiliary_recall = recall_auxiliary_candidates(
        db,
        execution_context.search_query_plan,
        project_id=execution_context.project_id,
        settings=execution_context.effective_settings,
        folder_photo_subquery=execution_context.folder_photo_subquery,
        constrained_photo_ids=execution_context.constrained_photo_ids,
        concept_terms=execution_context.concept_terms_for_debug,
        concept_facets=execution_context.concept_facets_for_debug,
        concept_entity_terms=execution_context.concept_entity_terms_for_debug,
        concept_recall_service_cls=ConceptRecallService,
        people_visual_recall_service_cls=PeopleVisualRecallService,
    )
    concept_results = auxiliary_recall.concept_results
    people_visual_results = auxiliary_recall.people_visual_results

    merged_keyword_results = merge_keyword_with_aux_candidates(
        keyword_results,
        concept_results,
        aux_source="concept",
    )
    merged_keyword_results = merge_keyword_with_aux_candidates(
        merged_keyword_results,
        people_visual_results,
        aux_source="people_visual",
    )

    keyword_query_terms = list(execution_context.search_query_plan.recall_terms)
    trace_writer.write_stage(
        "keyword_recall",
        candidates=len(keyword_results),
        keyword_query_text=" ".join(keyword_query_terms),
        keyword_query_terms=keyword_query_terms,
        top_scores=[round(candidate.keyword_score, 4) for candidate in keyword_results[:5]],
        duration_ms=_elapsed_ms(started_at),
    )
    trace_writer.extend(auxiliary_recall.trace_events)

    logger.debug(
        "[search] keyword_recall candidates=%d top_scores=%s",
        len(keyword_results),
        [round(candidate.keyword_score, 4) for candidate in keyword_results[:5]],
    )

    return KeywordAuxiliaryStageResult(
        keyword_results=keyword_results,
        merged_keyword_results=merged_keyword_results,
        concept_results=concept_results,
        people_visual_results=people_visual_results,
        concept_candidates_count=auxiliary_recall.concept_candidates_count,
        people_visual_candidates_count=auxiliary_recall.people_visual_candidates_count,
        concept_debug_info=auxiliary_recall.concept_debug,
    )


def run_vector_stage(
    db: Session,
    *,
    execution_context: SearchExecutionContext,
    trace_writer: SearchDebugTraceWriter,
) -> VectorStageResult:
    """Run vector recall stage with graceful fallback signaling."""
    started_at = perf_counter()
    vector_service = VectorRecallService(db, execution_context.effective_settings)
    is_ocr_query = execution_context.search_query_plan.intent == "ocr_text_search"
    uses_v2_contract = (
        str(getattr(execution_context.search_query_plan, "planner_contract_version", "1"))
        == "2"
    )
    semantic_plan = getattr(execution_context.search_query_plan, "semantic_plan", None) or {}
    semantic_queries = [
        str(item).strip()
        for item in list(semantic_plan.get("queries") or [])
        if str(item).strip()
    ]
    vector_query_text = (
        " ".join(dict.fromkeys(semantic_queries))
        if uses_v2_contract
        else str(execution_context.search_query_plan.semantic_query_text or "").strip()
    )
    vector_query_source = (
        str(
            (getattr(execution_context.search_query_plan, "planner_debug", None) or {}).get(
                "semantic_source"
            )
            or "qwen"
        )
        if uses_v2_contract
        else (
            "semantic_query_text" if vector_query_text else "legacy_query_fallback"
        )
    )
    raw_vector_top_k_per_field = max(
        1,
        int(execution_context.effective_settings.vector_top_k),
    )
    final_vector_top_k = raw_vector_top_k_per_field

    if uses_v2_contract and not vector_query_text:
        trace_writer.write_stage(
            "vector_recall",
            candidates=0,
            vector_candidates=0,
            vector_query_text="",
            vector_query_source="none",
            skipped=True,
            skip_reason="semantic_queries_empty",
            fallback=False,
            error="",
            duration_ms=_elapsed_ms(started_at),
        )
        return VectorStageResult(
            vector_scores={},
            embedding_model="",
            fallback_reason="semantic_queries_empty",
            stale_embedding_filtered=0,
            error=None,
        )

    logger.debug(
        "[search] vector_recall start is_ocr=%s project_id=%s",
        is_ocr_query,
        execution_context.project_id,
    )

    try:
        vector_scores, embedding_model, fallback_reason, stale_embedding_filtered = vector_service.search(
            query=(
                vector_query_text
                if uses_v2_contract
                else execution_context.search_query_plan.original_query
            ),
            normalized_query=(
                vector_query_text
                if uses_v2_contract
                else execution_context.search_query_plan.normalized_query
            ),
            semantic_query_text=vector_query_text,
            is_ocr_query=is_ocr_query,
            query_intent=execution_context.search_query_plan.intent,
            recommended_profile=execution_context.search_query_plan.recommended_profile,
            project_id=execution_context.project_id,  # type: ignore[arg-type]
            folder_photo_subquery=execution_context.folder_photo_subquery,
            constrained_photo_ids=execution_context.constrained_photo_ids,
            limit=raw_vector_top_k_per_field,
        )

        if len(vector_scores) > final_vector_top_k:
            top_items = sorted(
                vector_scores.items(),
                key=lambda item: item[1].total_score,
                reverse=True,
            )[:final_vector_top_k]
            vector_scores = {photo_id: scores for photo_id, scores in top_items}

        trace_writer.write_stage(
            "vector_recall",
            candidates=len(vector_scores),
            vector_candidates=len(vector_scores),
            raw_vector_top_k_per_field=raw_vector_top_k_per_field,
            final_vector_top_k=final_vector_top_k,
            embedding_model=embedding_model,
            is_ocr=is_ocr_query,
            stale_embedding_filtered=stale_embedding_filtered,
            vector_query_text=vector_query_text,
            vector_query_source=vector_query_source,
            fallback=False,
            error="",
            duration_ms=_elapsed_ms(started_at),
        )
        logger.debug(
            "[search] vector_recall done candidates=%d embedding_model=%s stale_filtered=%d",
            len(vector_scores),
            embedding_model,
            stale_embedding_filtered,
        )
        return VectorStageResult(
            vector_scores=vector_scores,
            embedding_model=embedding_model,
            fallback_reason=fallback_reason,
            stale_embedding_filtered=stale_embedding_filtered,
            error=None,
        )
    except (EmbeddingRequestError, SQLAlchemyError, RuntimeError) as exc:
        fallback_reason = str(exc)
        trace_writer.write_stage(
            "vector_recall",
            error=fallback_reason,
            fallback=True,
            embedding_model="",
            stale_embedding_filtered=0,
            vector_candidates=0,
            raw_vector_top_k_per_field=raw_vector_top_k_per_field,
            final_vector_top_k=final_vector_top_k,
            vector_query_text=vector_query_text,
            vector_query_source=vector_query_source,
            duration_ms=_elapsed_ms(started_at),
        )
        return VectorStageResult(
            vector_scores={},
            embedding_model="",
            fallback_reason=fallback_reason,
            stale_embedding_filtered=0,
            error=exc,
        )
