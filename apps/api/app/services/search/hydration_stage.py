"""Terminal hydration stage for search pipeline results."""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy.orm import Session

from .execution_context import SearchExecutionContext
from .pipeline_types import SearchPipelineDeps, SearchPipelineResult
from .trace_writer import SearchDebugTraceWriter
from .types import SearchCandidate, VectorMatchScores


class HydrationStage:
    def __init__(self, deps: SearchPipelineDeps) -> None:
        self._deps = deps

    def build_response(self, db: Session, candidates: list[SearchCandidate], **kwargs):
        return self._deps.build_result_response(db, candidates, **kwargs)

    def build_items(self, db: Session, candidates: list[SearchCandidate], **kwargs):
        return self._deps.build_result_items(db, candidates, **kwargs)

    def metadata_only_result(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        *,
        execution_context: SearchExecutionContext,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace: list[dict],
        debug_factory: Callable[..., dict],
    ) -> SearchPipelineResult:
        total, items, debug_payload = self.build_response(
            db,
            candidates,
            project_id=project_id or 0,
            result_mode="hybrid",
            path="metadata-only",
            page=page,
            page_size=page_size,
            debug=debug,
            trace=trace,
            debug_factory=debug_factory,
            debug_kwargs={
                "mode": "metadata",
                "keyword_candidates": 0,
                "vector_candidates": 0,
                "merged_candidates": len(candidates),
                "fallback_reason": "",
                "metadata_filters": execution_context.metadata_filters,
                "metadata_candidates": len(candidates),
                "metadata_only": True,
            },
        )
        return SearchPipelineResult(total, items, debug_payload)

    def people_only_result(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        *,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace: list[dict],
        debug_factory: Callable[..., dict],
    ) -> SearchPipelineResult:
        total, items, debug_payload = self.build_response(
            db,
            candidates,
            project_id=project_id or 0,
            result_mode="hybrid",
            path="people-only",
            page=page,
            page_size=page_size,
            debug=debug,
            trace=trace,
            debug_factory=debug_factory,
            debug_kwargs={
                "mode": "people",
                "keyword_candidates": 0,
                "vector_candidates": 0,
                "merged_candidates": len(candidates),
                "fallback_reason": "",
            },
        )
        return SearchPipelineResult(total, items, debug_payload)

    def keyword_only_result(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        *,
        execution_context: SearchExecutionContext,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace_writer: SearchDebugTraceWriter,
        debug_factory: Callable[..., dict],
        keyword_candidates_count: int,
    ) -> SearchPipelineResult:
        candidates = self._deps.attach_people_explain(candidates, execution_context.people_results)
        total, items = self.build_items(
            db,
            candidates,
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
        debug_payload = None
        if debug:
            debug_payload = debug_factory(
                mode="keyword",
                keyword_candidates=keyword_candidates_count,
                vector_candidates=0,
                merged_candidates=len(candidates),
                fallback_reason="",
            )
        return SearchPipelineResult(total, items, debug_payload)

    def vector_only_result(
        self,
        db: Session,
        vector_scores: dict[int, VectorMatchScores],
        *,
        execution_context: SearchExecutionContext,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace_writer: SearchDebugTraceWriter,
        debug_factory: Callable[..., dict],
        embedding_model: str,
        keyword_candidates_count: int,
    ) -> SearchPipelineResult:
        vector_only = self._vector_scores_to_candidates(vector_scores)
        vector_only = self._deps.attach_people_explain(vector_only, execution_context.people_results)
        total, items = self.build_items(
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
            debug_payload = debug_factory(
                mode="vector",
                embedding_model=embedding_model,
                keyword_candidates=keyword_candidates_count,
                vector_candidates=len(vector_scores),
                merged_candidates=len(vector_only),
                displayed_candidates=total,
                fallback_reason="",
            )
        return SearchPipelineResult(total, items, debug_payload)

    def hybrid_result(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        *,
        project_id: Optional[int],
        page: int,
        page_size: int,
        debug: bool,
        trace_writer: SearchDebugTraceWriter,
        debug_factory: Callable[..., dict],
        embedding_model: str,
        keyword_candidates_count: int,
        vector_candidates_count: int,
        filtered_count: int,
        filtered_out: list[SearchCandidate],
        vector_only_rejected_count: int,
        vector_only_reject_reasons: dict,
        stale_embedding_filtered: int,
    ) -> SearchPipelineResult:
        total, items = self.build_items(
            db,
            candidates,
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
            debug_payload = debug_factory(
                mode="hybrid",
                embedding_model=embedding_model,
                keyword_candidates=keyword_candidates_count,
                vector_candidates=vector_candidates_count,
                merged_candidates=len(candidates),
                fallback_reason="",
                displayed_candidates=total,
                filtered_candidates=filtered_count,
                vector_only_rejected_count=vector_only_rejected_count,
                vector_only_reject_reasons=vector_only_reject_reasons,
                filtered_out_samples=filtered_samples,
                stale_embedding_filtered=stale_embedding_filtered,
            )
        return SearchPipelineResult(total, items, debug_payload)

    def _vector_scores_to_candidates(
        self,
        vector_scores: dict[int, VectorMatchScores],
    ) -> list[SearchCandidate]:
        return [
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
                vector_scores.items(),
                key=lambda item: item[1].total_score,
                reverse=True,
            )
        ]
