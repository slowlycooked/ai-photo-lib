"""Typed contracts for the search pipeline boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Type

from .fallback_policy import SearchFallbackPolicy
from .types import SearchMode


@dataclass(frozen=True)
class SearchPipelineDeps:
    build_search_plan: Callable
    settings_resolver_cls: type
    query_plan_resolver: Callable
    understander: Callable
    people_query_resolver: Callable
    people_resolution_cls: type
    resolve_folder_photo_subquery: Callable
    resolve_face_filter_photo_ids: Callable
    resolve_structured_filter_photo_ids: Callable
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


@dataclass(frozen=True)
class SearchPipelineRequest:
    query: str
    page: int = 1
    page_size: int = 50
    project_id: Optional[int] = None
    folder_id: Optional[int] = None
    folder_scope: str = "subtree"
    mode: SearchMode = "hybrid"
    debug: bool = False
    face_count_min: Optional[int] = None
    face_count_max: Optional[int] = None
    has_review_pending: Optional[bool] = None
    has_unnamed_people: Optional[bool] = None


@dataclass(frozen=True)
class SearchPipelineResult:
    total: int
    items: list
    debug_payload: Optional[dict]

    def as_tuple(self) -> tuple[int, list, Optional[dict]]:
        return self.total, self.items, self.debug_payload
