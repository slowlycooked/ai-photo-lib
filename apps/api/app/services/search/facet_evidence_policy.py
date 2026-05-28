"""Facet and evidence policy wrappers for search post-fusion filtering."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ...models.ai import PhotoAIAnalysis
from .filter_policy import (
    apply_evidence_scoring,
    apply_semantic_tag_boost,
    compute_evidence_level,
    core_facet_passes,
)
from .query_understanding import SearchQueryPlan
from .types import EffectiveSearchSettings, SearchCandidate


class FacetEvidencePolicy:
    """Thin wrapper around filter-policy functions used by the search orchestrator."""

    def core_facet_passes(
        self,
        candidate: SearchCandidate,
        ai_analysis: Optional[PhotoAIAnalysis],
        query_plan: SearchQueryPlan,
        settings: EffectiveSearchSettings,
    ) -> tuple[bool, str]:
        return core_facet_passes(candidate, ai_analysis, query_plan, settings)

    def compute_evidence_level(
        self,
        candidate: SearchCandidate,
        settings: Optional[EffectiveSearchSettings] = None,
    ) -> str:
        return compute_evidence_level(candidate, settings)

    def apply_evidence_scoring(
        self,
        candidates: list[SearchCandidate],
        settings: EffectiveSearchSettings,
    ) -> list[SearchCandidate]:
        return apply_evidence_scoring(candidates, settings)

    def apply_semantic_tag_boost(
        self,
        db: Session,
        candidates: list[SearchCandidate],
        query_plan: SearchQueryPlan,
        project_id: int,
    ) -> list[SearchCandidate]:
        return apply_semantic_tag_boost(db, candidates, query_plan, project_id)
