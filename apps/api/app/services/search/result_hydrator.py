"""Result hydrator — converts SearchCandidate list to serialisable dicts."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ...logging_config import should_include_search_debug_payload
from ...models.ai import PhotoAIAnalysis
from ...models.photo import Photo
from .types import SearchCandidate, SearchMode

# Evidence level → human-readable rank reason
_RANK_REASON: dict[str, str] = {
    "A": "exact query term matched",
    "B": "strong expanded term matched",
    "C": "strong vector semantic match",
    "D": "only weak/broad term matched, not primary evidence",
    "E": "only weak vector signal, filtered",
}


def build_result_items(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    project_id: int,
    mode: SearchMode,
    page: int,
    page_size: int,
    debug: bool,
) -> tuple[int, list[dict]]:
    """Paginate *candidates* and load photo rows.

    Returns (total_count, page_items).
    """
    total = len(candidates)
    if total == 0:
        return 0, []

    offset = (page - 1) * page_size
    page_candidates = candidates[offset : offset + page_size]
    if not page_candidates:
        return total, []

    photo_ids = [c.photo_id for c in page_candidates]
    rows = (
        db.query(Photo, PhotoAIAnalysis)
        .outerjoin(
            PhotoAIAnalysis,
            (PhotoAIAnalysis.photo_id == Photo.id)
            & (PhotoAIAnalysis.project_id == Photo.project_id),
        )
        .filter(
            Photo.id.in_(photo_ids),
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
        .all()
    )
    row_by_photo_id = {photo.id: (photo, ai) for photo, ai in rows}

    items: list[dict] = []
    for candidate in page_candidates:
        pair = row_by_photo_id.get(candidate.photo_id)
        if pair is None:
            continue
        photo, ai = pair

        thumb = (
            f"/api/projects/{project_id}/photos/{photo.id}/thumbnail"
            f"?v={int(photo.updated_at.timestamp()) if photo.updated_at else 0}"
        )

        if mode == "vector":
            score = candidate.vector_score
        elif mode == "hybrid":
            score = candidate.final_score
        else:
            score = candidate.keyword_score

        item: dict = {
            "photo_id": photo.id,
            "file_name": photo.file_name,
            "thumbnail_url": thumb,
            "updated_at": photo.updated_at,
            "taken_at": photo.taken_at,
            "width": photo.width,
            "height": photo.height,
            "caption": ai.caption if ai else None,
            "matched_tags": candidate.matched_tags,
            "score": round(float(score), 6),
            # EXIF / metadata fields
            "camera_make": photo.camera_make,
            "camera_model": photo.camera_model,
            "lens_model": photo.lens_model,
            "focal_length": photo.focal_length,
            "aperture": photo.aperture,
            "exposure_time": photo.exposure_time,
            "iso": photo.iso,
            "gps_latitude": photo.gps_latitude,
            "gps_longitude": photo.gps_longitude,
            # P2: evidence level always present (frontend uses for fold/filter UI)
            "evidence_level": candidate.evidence_level or "E",
        }

        if debug and should_include_search_debug_payload():
            item["keyword_score"] = round(float(candidate.keyword_score), 6)
            item["vector_score"] = round(float(candidate.vector_score), 6)
            item["rrf_score"] = round(float(candidate.rrf_score), 6)
            item["match_source"] = list(candidate.match_source)
            item["should_display"] = (candidate.evidence_level or "E") not in ("D", "E", "F")
            item["rank_reason"] = _RANK_REASON.get(candidate.evidence_level or "E", "unknown")
            item["filter_reason"] = candidate.filter_reason
            # Five-tier term breakdown
            if candidate.term_level_hits:
                item["term_level_hits"] = {
                    k: list(v) for k, v in candidate.term_level_hits.items() if v
                }
            if candidate.field_scores:
                item["field_scores"] = candidate.field_scores
            # Evidence scoring breakdown
            if candidate.score_breakdown:
                item["score_breakdown"] = candidate.score_breakdown
            # Negative-term hits and core facet check
            if candidate.negative_hits:
                item["negative_hits"] = list(candidate.negative_hits)
            if candidate.core_facet_passed is not None:
                item["core_facet_passed"] = candidate.core_facet_passed
            # Per-result explain payload
            explain: dict = {}
            if candidate.keyword_explain:
                explain["keyword"] = {
                    "matched_fields": candidate.keyword_explain,
                    "rank": candidate.keyword_rank,
                }
            if candidate.vector_explain:
                explain["vector"] = {
                    "field_scores": candidate.vector_explain,
                    "rank": candidate.vector_rank,
                }
            if explain:
                item["explain"] = explain

        items.append(item)

    return total, items
