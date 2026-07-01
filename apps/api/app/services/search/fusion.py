"""RRF fusion of keyword and vector recall lists."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .types import EffectiveSearchSettings, SearchCandidate, VectorMatchScores

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FusionResult:
    candidates: list[SearchCandidate]
    trace_event: dict


def rrf_merge(
    keyword_results: list[SearchCandidate],
    vector_scores: dict[int, VectorMatchScores],
    settings: EffectiveSearchSettings,
    people_results: Optional[list[SearchCandidate]] = None,
    people_weight: float = 1.20,
) -> list[SearchCandidate]:
    """Reciprocal Rank Fusion.

    Merges a keyword ranked list and a vector score dict using per-project
    *keyword_weight*, *vector_weight* and *rrf_k* from *settings*.
    """
    logger.debug(
        "[fusion] rrf_merge kw_results=%d vec_results=%d people_results=%d rrf_k=%d kw_weight=%.2f vec_weight=%.2f people_weight=%.2f",
        len(keyword_results), len(vector_scores), len(people_results or []),
        settings.rrf_k, settings.keyword_weight, settings.vector_weight, people_weight,
    )
    merged: dict[int, SearchCandidate] = {}
    rrf_k = settings.rrf_k

    for rank, candidate in enumerate(keyword_results, start=1):
        fused = settings.keyword_weight / (rrf_k + rank)
        row = merged.get(candidate.photo_id)
        if row is None:
            row = SearchCandidate(photo_id=candidate.photo_id)
            merged[candidate.photo_id] = row
        row.keyword_score = candidate.keyword_score
        row.matched_tags = list(candidate.matched_tags)
        row.keyword_explain = dict(candidate.keyword_explain)
        row.keyword_rank = rank
        row.rrf_score += fused
        row.final_score = row.rrf_score
        # P2: propagate tier tracking from keyword recall
        row.hit_tiers = row.hit_tiers | candidate.hit_tiers
        if candidate.term_level_hits:
            for tier, terms in candidate.term_level_hits.items():
                existing = row.term_level_hits.setdefault(tier, [])
                for t in terms:
                    if t not in existing:
                        existing.append(t)
        for source_name in candidate.match_source or ["keyword"]:
            if source_name not in row.match_source:
                row.match_source.append(source_name)

    for rank, (photo_id, vector_match) in enumerate(
        sorted(vector_scores.items(), key=lambda x: x[1].total_score, reverse=True),
        start=1,
    ):
        fused = settings.vector_weight / (rrf_k + rank)
        row = merged.get(photo_id)
        if row is None:
            row = SearchCandidate(photo_id=photo_id)
            merged[photo_id] = row
        row.vector_score = vector_match.total_score
        row.vector_rank = rank
        row.rrf_score += fused
        row.final_score = row.rrf_score
        row.vector_explain = {
            "content": round(vector_match.content_score, 4),
            "caption": round(vector_match.caption_score, 4),
            "tag": round(vector_match.tag_score, 4),
            "ocr": round(vector_match.ocr_score, 4),
        }
        row.field_scores = dict(row.vector_explain)

        for source_name, score in (
            ("vector_content", vector_match.content_score),
            ("vector_caption", vector_match.caption_score),
            ("vector_tag", vector_match.tag_score),
            ("vector_ocr", vector_match.ocr_score),
        ):
            if score > 0 and source_name not in row.match_source:
                row.match_source.append(source_name)

    for rank, candidate in enumerate(people_results or [], start=1):
        fused = people_weight / (rrf_k + rank)
        row = merged.get(candidate.photo_id)
        if row is None:
            row = SearchCandidate(photo_id=candidate.photo_id)
            merged[candidate.photo_id] = row
        row.people_score = candidate.people_score
        row.people_rank = rank
        row.people_explain = dict(candidate.people_explain)
        row.rrf_score += fused
        row.final_score = row.rrf_score
        if "people" not in row.match_source:
            row.match_source.append("people")

    result = sorted(merged.values(), key=lambda item: item.final_score, reverse=True)
    logger.debug(
        "[fusion] rrf_merge done merged=%d top_scores=%s",
        len(result),
        [round(c.final_score, 6) for c in result[:5]],
    )
    if result and logger.isEnabledFor(5):  # TRACE level
        for c in result[:10]:
            logger.log(
                5,
                "[fusion] photo_id=%d final=%.6f kw_rank=%s vec_rank=%s kw_score=%.4f vec_score=%.4f sources=%s",
                c.photo_id, c.final_score,
                c.keyword_rank, c.vector_rank,
                c.keyword_score, c.vector_score,
                c.match_source,
            )
    return result


def fuse_hybrid_candidates(
    keyword_results: list[SearchCandidate],
    vector_scores: dict[int, VectorMatchScores],
    settings: EffectiveSearchSettings,
    *,
    concept_candidates_count: int,
    people_results: Optional[list[SearchCandidate]] = None,
    people_weight: float = 1.20,
) -> FusionResult:
    """Fuse hybrid recall results and build the matching debug trace event."""
    merged = rrf_merge(
        keyword_results,
        vector_scores,
        settings,
        people_results=people_results,
        people_weight=people_weight,
    )
    return FusionResult(
        candidates=merged,
        trace_event={
            "stage": "rrf_merge",
            "kw_candidates": len(keyword_results),
            "concept_candidates": concept_candidates_count,
            "vec_candidates": len(vector_scores),
            "people_candidates": len(people_results or []),
            "merged": len(merged),
            "top_final_scores": [round(candidate.final_score, 6) for candidate in merged[:5]],
            "rrf_k": settings.rrf_k,
            "kw_weight": settings.keyword_weight,
            "vec_weight": settings.vector_weight,
            "people_weight": people_weight,
        },
    )
