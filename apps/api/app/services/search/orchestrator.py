"""Stage orchestrator for project-scoped search."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Type

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .debug_builder import SearchDebugBuilder
from .execution_context import SearchExecutionContext
from .fallback_policy import SearchFallbackPolicy
from .query_understanding import build_query_plan_trace_event
from .trace_writer import SearchDebugTraceWriter
from .types import SearchCandidate, SearchMode

logger = logging.getLogger(__name__)

_PEOPLE_RRF_WEIGHT = 1.20


@dataclass(frozen=True)
class SearchOrchestratorDeps:
    build_search_plan: Callable
    settings_resolver_cls: type
    query_plan_resolver: Callable
    understander: Callable
    people_query_resolver: Callable
    people_resolution_cls: type
    resolve_folder_photo_subquery: Callable
    resolve_face_filter_photo_ids: Callable
    derive_concept_query_context: Callable
    run_metadata_stage: Callable
    run_people_stage: Callable
    run_keyword_auxiliary_stage: Callable
    run_vector_stage: Callable
    build_result_response: Callable
    build_result_items: Callable
    attach_people_explain: Callable
    fuse_hybrid_candidates: Callable
    apply_post_fusion_pipeline: Callable
    fallback_policy_cls: Type[SearchFallbackPolicy] = SearchFallbackPolicy


class SearchOrchestrator:
    """Coordinates search stages while delegating policy logic to specialized modules."""

    def __init__(self, db: Session, deps: SearchOrchestratorDeps) -> None:
        self._db = db
        self._deps = deps
        self._fallback_policy = deps.fallback_policy_cls(db)

    def search(
        self,
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
        query = query.strip()
        if not query:
            return 0, [], None

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

        plan = self._deps.build_search_plan(
            self._db,
            query=query,
            mode=mode,
            project_id=project_id,
            face_filter_active=face_filter_active,
            settings_resolver_cls=self._deps.settings_resolver_cls,
            query_plan_resolver=self._deps.query_plan_resolver,
            understander=self._deps.understander,
            people_query_resolver=self._deps.people_query_resolver,
            people_resolution_cls=self._deps.people_resolution_cls,
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
            self._deps.resolve_folder_photo_subquery(
                self._db,
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
                    self._db.query(func.count())
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

        if project_id is not None and face_filter_active:
            face_filter_photo_ids = self._deps.resolve_face_filter_photo_ids(
                self._db,
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

        if execution_context.metadata_only_requested and not execution_context.metadata_only_allowed:
            logger.debug(
                "[search] metadata_only ignored due to semantic intent=%s",
                execution_context.search_query_plan.intent,
            )

        (
            concept_terms_for_debug,
            concept_entity_terms_for_debug,
            concept_facets_for_debug,
        ) = self._deps.derive_concept_query_context(execution_context.search_query_plan)
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

        debug_builder = SearchDebugBuilder(logger, execution_context, trace)

        def _build_debug_payload(**kwargs) -> dict:
            return debug_builder.build(**kwargs)

        metadata_stage = self._deps.run_metadata_stage(
            self._db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        execution_context.constrained_photo_ids = metadata_stage.constrained_photo_ids
        if metadata_stage.metadata_only_candidates is not None:
            logger.debug("[search] path=metadata-only filters=%s", execution_context.metadata_filters)
            total, items, debug_payload = self._deps.build_result_response(
                self._db,
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

        people_stage = self._deps.run_people_stage(
            self._db,
            execution_context=execution_context,
            trace_writer=trace_writer,
        )
        execution_context.constrained_photo_ids = people_stage.constrained_photo_ids
        execution_context.people_results = people_stage.people_results
        execution_context.matched_person_ids = people_stage.matched_person_ids
        execution_context.people_candidates_debug = people_stage.people_candidates_debug
        if people_stage.people_only_candidates is not None:
            total, items, debug_payload = self._deps.build_result_response(
                self._db,
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
            keyword_stage = self._deps.run_keyword_auxiliary_stage(
                self._db,
                execution_context=execution_context,
                trace_writer=trace_writer,
            )
            keyword_results = keyword_stage.keyword_results
            merged_keyword_results = keyword_stage.merged_keyword_results
            concept_results = keyword_stage.concept_results
            execution_context.concept_candidates_count = keyword_stage.concept_candidates_count
            execution_context.people_visual_candidates_count = keyword_stage.people_visual_candidates_count
            execution_context.concept_debug_info = keyword_stage.concept_debug_info
        except SQLAlchemyError as exc:
            fallback_result = self._fallback_policy.handle_keyword_stage_error(
                error=exc,
                execution_context=execution_context,
                query=query,
                project_id=project_id,
                folder_photo_subquery=folder_photo_subquery,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_builder=debug_builder,
                build_result_items_fn=self._deps.build_result_items,
            )
            if fallback_result is not None:
                return fallback_result
            raise

        if execution_context.effective_mode == "keyword" or project_id is None:
            logger.debug("[search] path=keyword-only")
            total, items = self._deps.build_result_items(
                self._db,
                self._deps.attach_people_explain(merged_keyword_results, execution_context.people_results),
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

        vector_stage = self._deps.run_vector_stage(
            self._db,
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
                "Vector search fallback to keyword. project_id=%s query=%r error=%s error_type=%s error_repr=%r",
                project_id,
                query,
                exc,
                type(exc).__name__,
                exc,
            )
            return self._fallback_policy.handle_vector_stage_error(
                error=exc,
                execution_context=execution_context,
                keyword_results=keyword_results,
                merged_keyword_results=merged_keyword_results,
                embedding_model=embedding_model,
                fallback_reason=fallback_reason,
                project_id=project_id,
                page=page,
                page_size=page_size,
                debug=debug,
                trace_writer=trace_writer,
                debug_builder=debug_builder,
                attach_people_explain=self._deps.attach_people_explain,
                build_result_items_fn=self._deps.build_result_items,
            )

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
            vector_only = self._deps.attach_people_explain(vector_only, execution_context.people_results)
            total, items = self._deps.build_result_items(
                self._db,
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

        logger.debug(
            "[search] path=hybrid rrf_merge kw_candidates=%d vec_candidates=%d people_candidates=%d",
            len(merged_keyword_results), len(vector_scores), len(execution_context.people_results),
        )
        fusion_result = self._deps.fuse_hybrid_candidates(
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
            [round(candidate.final_score, 6) for candidate in merged[:5]],
        )
        trace_writer.write(fusion_result.trace_event)

        post_fusion = self._deps.apply_post_fusion_pipeline(
            self._db,
            merged,
            query_plan=execution_context.search_query_plan,
            settings=execution_context.effective_settings,
            project_id=project_id,
        )
        merged = post_fusion.candidates
        filtered_out = post_fusion.filtered_out
        filtered_count = post_fusion.filtered_count
        trace_writer.extend(post_fusion.trace_events)

        total, items = self._deps.build_result_items(
            self._db,
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
            filtered_samples = [
                {
                    "photo_id": candidate.photo_id,
                    "evidence_level": candidate.evidence_level,
                    "filter_reason": candidate.filter_reason,
                    "vector_score": round(candidate.vector_score, 4),
                    "keyword_score": round(candidate.keyword_score, 4),
                }
                for candidate in filtered_out[:10]
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
                filtered_out_samples=filtered_samples,
                stale_embedding_filtered=stale_embedding_filtered,
            )
        logger.debug(
            "[search] ── DONE ── path=hybrid total=%d items=%d page=%d",
            total, len(items), page,
        )
        return total, items, debug_payload
