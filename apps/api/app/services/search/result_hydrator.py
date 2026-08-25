"""Result hydrator — converts SearchCandidate list to serialisable dicts."""
from __future__ import annotations

from typing import Callable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...logging_config import should_include_search_debug_payload
from ...models.ai import PhotoAIAnalysis
from ...models.face import FaceDetection
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
    sort_specs: Optional[list[dict]] = None,
) -> tuple[int, list[dict]]:
    """Paginate *candidates* and load photo rows.

    Returns (total_count, page_items).
    """
    candidates = _sort_candidates(
        db,
        candidates,
        project_id=project_id,
        mode=mode,
        sort_specs=sort_specs or [],
    )
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
    try:
        face_counts = {
            int(photo_id): int(count)
            for photo_id, count in (
                db.query(FaceDetection.photo_id, func.count(FaceDetection.id))
                .filter(
                    FaceDetection.project_id == project_id,
                    FaceDetection.photo_id.in_(photo_ids),
                    FaceDetection.status != "failed",
                )
                .group_by(FaceDetection.photo_id)
                .all()
            )
        }
    except Exception:  # noqa: BLE001
        face_counts = {}

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
            "country_name": photo.country_name,
            "admin1": photo.admin1,
            "admin2": photo.admin2,
            "city": photo.city,
            "district": photo.district,
            "formatted_address": photo.formatted_address,
            "face_count": face_counts.get(photo.id, 0),
            # P2: evidence level always present (frontend uses for fold/filter UI)
            "evidence_level": candidate.evidence_level or "E",
            "matched_people": list(candidate.people_explain.get("matched_people", [])),
        }

        if debug and should_include_search_debug_payload():
            item["keyword_score"] = round(float(candidate.keyword_score), 6)
            item["vector_score"] = round(float(candidate.vector_score), 6)
            item["people_score"] = round(float(candidate.people_score), 6)
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
            if candidate.people_explain:
                explain["people"] = {
                    "matched_people": list(candidate.people_explain.get("matched_people", [])),
                    "rank": candidate.people_rank,
                    "people_filter_mode": candidate.people_explain.get("people_filter_mode"),
                }
            if explain:
                item["explain"] = explain

        items.append(item)

    return total, items


def _candidate_relevance(candidate: SearchCandidate, mode: SearchMode) -> float:
    if mode == "vector":
        return float(candidate.vector_score)
    if mode == "hybrid":
        return float(candidate.final_score)
    return float(candidate.keyword_score)


def _sort_candidates(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    project_id: int,
    mode: SearchMode,
    sort_specs: list[dict],
) -> list[SearchCandidate]:
    """Apply validated sort specs before pagination; preserve relevance by default."""
    if not candidates or not sort_specs:
        return candidates

    supported_specs = [
        spec for spec in sort_specs
        if spec.get("field") in {"relevance", "taken_at", "created_at"}
        and spec.get("order") in {"asc", "desc"}
    ]
    if not supported_specs:
        return candidates

    timestamp_fields = {
        str(spec["field"])
        for spec in supported_specs
        if spec.get("field") in {"taken_at", "created_at"}
    }
    timestamps: dict[int, dict[str, object]] = {}
    if timestamp_fields:
        rows = (
            db.query(Photo.id, Photo.taken_at, Photo.created_at)
            .filter(
                Photo.project_id == project_id,
                Photo.deleted_at.is_(None),
                Photo.id.in_([candidate.photo_id for candidate in candidates]),
            )
            .all()
        )
        timestamps = {
            int(photo_id): {"taken_at": taken_at, "created_at": created_at}
            for photo_id, taken_at, created_at in rows
        }

    ordered = list(candidates)
    for spec in reversed(supported_specs):
        field = str(spec["field"])
        reverse = spec["order"] == "desc"
        if field == "relevance":
            ordered.sort(key=lambda candidate: _candidate_relevance(candidate, mode), reverse=reverse)
            continue

        with_value = [
            candidate
            for candidate in ordered
            if timestamps.get(candidate.photo_id, {}).get(field) is not None
        ]
        with_value_ids = {candidate.photo_id for candidate in with_value}
        without_value = [candidate for candidate in ordered if candidate.photo_id not in with_value_ids]
        with_value.sort(
            key=lambda candidate: timestamps[candidate.photo_id][field],
            reverse=reverse,
        )
        ordered = with_value + without_value
    return ordered


def build_result_response(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    project_id: int,
    result_mode: SearchMode,
    path: str,
    page: int,
    page_size: int,
    debug: bool,
    trace: list[dict],
    debug_factory: Optional[Callable[..., dict]] = None,
    debug_kwargs: Optional[dict] = None,
    sort_specs: Optional[list[dict]] = None,
) -> tuple[int, list[dict], Optional[dict]]:
    """Hydrate candidates, append result trace, and optionally build debug payload."""
    total, items = build_result_items(
        db,
        candidates,
        project_id=project_id,
        mode=result_mode,
        page=page,
        page_size=page_size,
        debug=debug,
        sort_specs=sort_specs,
    )
    trace.append(
        {
            "stage": "result",
            "path": path,
            "total": total,
            "items_in_page": len(items),
            "page": page,
        }
    )
    debug_payload = (
        debug_factory(**(debug_kwargs or {}))
        if debug and debug_factory is not None
        else None
    )
    return total, items, debug_payload


def build_empty_result_response(
    *,
    path: str,
    page: int,
    debug: bool,
    trace: list[dict],
    debug_factory: Optional[Callable[..., dict]] = None,
    debug_kwargs: Optional[dict] = None,
) -> tuple[int, list[dict], Optional[dict]]:
    """Return an empty result response with the standard result trace shape."""
    trace.append(
        {
            "stage": "result",
            "path": path,
            "total": 0,
            "items_in_page": 0,
            "page": page,
        }
    )
    debug_payload = (
        debug_factory(**(debug_kwargs or {}))
        if debug and debug_factory is not None
        else None
    )
    return 0, [], debug_payload
