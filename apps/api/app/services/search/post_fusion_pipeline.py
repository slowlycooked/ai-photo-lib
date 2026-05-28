"""Post-fusion filtering pipeline for hybrid search results."""
from __future__ import annotations

import logging
from dataclasses import dataclass
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
from .types import EffectiveSearchSettings, SearchCandidate, evidence_level_passes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostFusionPipelineResult:
    candidates: list[SearchCandidate]
    filtered_out: list[SearchCandidate]
    filtered_count: int
    trace_events: list[dict]


def apply_post_fusion_pipeline(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    query_plan: SearchQueryPlan,
    settings: EffectiveSearchSettings,
    project_id: Optional[int],
) -> PostFusionPipelineResult:
    """Apply post-fusion ranking and filtering stages for hybrid search."""
    merged = list(candidates)

    for candidate in merged:
        candidate.evidence_level = compute_evidence_level(candidate, settings)

    if settings.enable_evidence_filter:
        merged = apply_evidence_scoring(merged, settings)

    pre_filter_count = len(merged)
    min_level = settings.min_display_evidence_level
    filtered_out: list[SearchCandidate] = []
    kept: list[SearchCandidate] = []
    for candidate in merged:
        if evidence_level_passes(candidate.evidence_level or "E", min_level):
            kept.append(candidate)
        else:
            candidate.filter_reason = (
                f"evidence_level:{candidate.evidence_level} below min:{min_level}"
            )
            filtered_out.append(candidate)
    merged = kept
    filtered_count = pre_filter_count - len(merged)

    if filtered_count:
        logger.debug(
            "[search] evidence_filter removed %d candidates below level %s (%d remaining)",
            filtered_count,
            min_level,
            len(merged),
        )

    trace_events: list[dict] = [
        {
            "stage": "evidence_filter",
            "pre_filter": pre_filter_count,
            "min_display_level": min_level,
            "filtered_count": filtered_count,
            "remaining": len(merged),
            "level_distribution": {
                level: sum(1 for candidate in merged if candidate.evidence_level == level)
                for level in ("A", "B", "C", "D", "E", "F")
            },
            "filtered_level_distribution": {
                level: sum(1 for candidate in filtered_out if candidate.evidence_level == level)
                for level in ("D", "E", "F")
            },
        }
    ]

    core_facet_filtered = 0
    if merged and query_plan.core_facets and project_id is not None:
        photo_ids_for_facet = [candidate.photo_id for candidate in merged]
        ai_rows_for_facet = (
            db.query(PhotoAIAnalysis)
            .filter(
                PhotoAIAnalysis.photo_id.in_(photo_ids_for_facet),
                PhotoAIAnalysis.project_id == project_id,
            )
            .all()
        )
        ai_by_id_facet: dict[int, PhotoAIAnalysis] = {
            row.photo_id: row for row in ai_rows_for_facet
        }
        kept_facet: list[SearchCandidate] = []
        for candidate in merged:
            ai_obj = ai_by_id_facet.get(candidate.photo_id)
            passes, reason = core_facet_passes(candidate, ai_obj, query_plan, settings)
            if passes:
                kept_facet.append(candidate)
            else:
                core_facet_filtered += 1
                candidate.filter_reason = f"core_facet_fail:{reason}"
                filtered_out.append(candidate)
        if core_facet_filtered:
            logger.debug(
                "[search] core_facet_filter removed %d candidates (%d remaining)",
                core_facet_filtered,
                len(kept_facet),
            )
            merged = kept_facet

        trace_events.append(
            {
                "stage": "core_facet_filter",
                "core_facets": query_plan.core_facets,
                "matched_keys": query_plan.matched_keys,
                "filtered": core_facet_filtered,
                "remaining": len(merged),
            }
        )

    filtered_count += core_facet_filtered

    if settings.enable_semantic_tag_boost and merged and project_id is not None:
        merged = apply_semantic_tag_boost(db, merged, query_plan, project_id)
        trace_events.append(
            {
                "stage": "semantic_tag_boost",
                "candidates": len(merged),
                "top_final_scores": [round(candidate.final_score, 6) for candidate in merged[:5]],
                "penalize_tags": query_plan.penalize_tags,
            }
        )
        logger.debug(
            "[search] semantic_tag_boost applied penalize_tags=%s",
            query_plan.penalize_tags,
        )

    return PostFusionPipelineResult(
        candidates=merged,
        filtered_out=filtered_out,
        filtered_count=filtered_count,
        trace_events=trace_events,
    )
