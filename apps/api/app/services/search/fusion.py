"""RRF fusion of keyword and vector recall lists."""
from __future__ import annotations

from .types import EffectiveSearchSettings, SearchCandidate, VectorMatchScores


def rrf_merge(
    keyword_results: list[SearchCandidate],
    vector_scores: dict[int, VectorMatchScores],
    settings: EffectiveSearchSettings,
) -> list[SearchCandidate]:
    """Reciprocal Rank Fusion.

    Merges a keyword ranked list and a vector score dict using per-project
    *keyword_weight*, *vector_weight* and *rrf_k* from *settings*.
    """
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
        if "keyword" not in row.match_source:
            row.match_source.append("keyword")

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

    return sorted(merged.values(), key=lambda item: item.final_score, reverse=True)
