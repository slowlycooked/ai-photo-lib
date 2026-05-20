from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

from sqlalchemy import func, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import PhotoAIAnalysis, ProjectAISettings
from ..models.photo import Photo
from ..services.embedding_client import EmbeddingRequestError, embed_text
from ..services.folder_service import apply_folder_filter

logger = logging.getLogger(__name__)

SearchMode = Literal["keyword", "vector", "hybrid"]

_VECTOR_FIELD_WEIGHTS = {
    "caption_embedding": 0.45,
    "tag_embedding": 0.40,
    "ocr_embedding": 0.15,
}

_WEIGHTS = {
    "caption": 3,
    "ocr_text": 5,
    "scene_tags": 4,
    "object_tags": 4,
    "activity_tags": 4,
    "search_keywords": 4,
    "quality_tags": 2,
    "location_clues": 2,
    "file_name": 1,
}

_MAX_PER_TERM = sum(_WEIGHTS.values())
_DB_EMBEDDING_DIMENSION = 1024


@dataclass
class SearchCandidate:
    photo_id: int
    keyword_score: float = 0.0
    vector_score: float = 0.0
    final_score: float = 0.0
    matched_tags: list[str] = field(default_factory=list)


def _build_any_match_filter(terms: list[str]):
    per_term = []
    for term in terms:
        like = f"%{term}%"
        per_term.append(
            or_(
                PhotoAIAnalysis.caption.ilike(like),
                PhotoAIAnalysis.ocr_text.ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.scene_tags, " "), "").ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.object_tags, " "), "").ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.activity_tags, " "), "").ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.search_keywords, " "), "").ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.quality_tags, " "), "").ilike(like),
                func.coalesce(func.array_to_string(PhotoAIAnalysis.location_clues, " "), "").ilike(like),
                Photo.file_name.ilike(like),
            )
        )
    return or_(*per_term)


def _score_result(photo: Photo, ai: PhotoAIAnalysis, terms: list[str]) -> tuple[float, list[str]]:
    raw = 0
    matched: set[str] = set()

    for term in terms:
        t = term.lower()

        if ai.caption and t in ai.caption.lower():
            raw += _WEIGHTS["caption"]
        if ai.ocr_text and t in ai.ocr_text.lower():
            raw += _WEIGHTS["ocr_text"]
        if photo.file_name and t in photo.file_name.lower():
            raw += _WEIGHTS["file_name"]

        for field, weight in (
            ("scene_tags", _WEIGHTS["scene_tags"]),
            ("object_tags", _WEIGHTS["object_tags"]),
            ("activity_tags", _WEIGHTS["activity_tags"]),
            ("search_keywords", _WEIGHTS["search_keywords"]),
            ("quality_tags", _WEIGHTS["quality_tags"]),
            ("location_clues", _WEIGHTS["location_clues"]),
        ):
            tags: list[str] | None = getattr(ai, field, None)
            if tags:
                for tag in tags:
                    if t in tag.lower():
                        raw += weight
                        matched.add(tag)

    max_possible = len(terms) * _MAX_PER_TERM
    score = round(min(raw / max_possible, 1.0), 4) if max_possible else 0.0
    return score, sorted(matched)


def _resolve_folder_photo_ids(
    db: Session,
    *,
    project_id: int | None,
    folder_id: int | None,
    folder_scope: str,
) -> set[int] | None:
    if folder_id is None:
        return None
    if project_id is None:
        return set()

    photo_query = db.query(Photo).filter(Photo.deleted_at.is_(None), Photo.project_id == project_id)
    photo_query = apply_folder_filter(photo_query, db, project_id, folder_id, folder_scope)
    return {p.id for p in photo_query.all()}


def _keyword_search(
    db: Session,
    query: str,
    *,
    project_id: int | None,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> list[SearchCandidate]:
    terms = [t for t in query.split() if t] or [query]

    base_query = (
        db.query(Photo, PhotoAIAnalysis)
        .join(PhotoAIAnalysis, PhotoAIAnalysis.photo_id == Photo.id)
        .filter(Photo.deleted_at.is_(None))
        .filter(_build_any_match_filter(terms))
    )

    if project_id is not None:
        base_query = base_query.filter(
            Photo.project_id == project_id,
            PhotoAIAnalysis.project_id == project_id,
        )

    if folder_photo_ids is not None:
        if not folder_photo_ids:
            return []
        base_query = base_query.filter(Photo.id.in_(folder_photo_ids))

    rows: list[tuple[Photo, PhotoAIAnalysis]] = (
        base_query
        .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .limit(limit)
        .all()
    )

    candidates: list[SearchCandidate] = []
    for photo, ai in rows:
        score, matched_tags = _score_result(photo, ai, terms)
        if score <= 0:
            continue
        candidates.append(
            SearchCandidate(
                photo_id=photo.id,
                keyword_score=score,
                matched_tags=matched_tags,
            )
        )

    candidates.sort(key=lambda item: item.keyword_score, reverse=True)
    return candidates


def _query_vector_literal(query_vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"


def _vector_search(
    db: Session,
    *,
    query: str,
    project_id: int,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> dict[int, float]:
    if settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Config mismatch: embedding_dimension must be {_DB_EMBEDDING_DIMENSION}, got {settings.embedding_dimension}"
        )

    settings_row = (
        db.query(ProjectAISettings)
        .filter(ProjectAISettings.project_id == project_id)
        .first()
    )
    endpoint_url = settings_row.endpoint_url if settings_row else None
    query_embedding = embed_text(
        query,
        endpoint_url=endpoint_url,
        model=settings.embedding_model or settings.openai_model,
        expected_dim=settings.embedding_dimension,
    )

    params: dict[str, object] = {
        "project_id": project_id,
        "query_vector": _query_vector_literal(query_embedding),
        "limit": limit,
    }

    folder_filter = ""
    if folder_photo_ids is not None:
        if not folder_photo_ids:
            return {}
        params["photo_ids"] = list(folder_photo_ids)
        folder_filter = " AND pe.photo_id = ANY(:photo_ids)"

    sql = text(
        """
        WITH caption AS (
            SELECT pe.photo_id,
                   (1 - (pe.caption_embedding <=> CAST(:query_vector AS vector))) * :caption_weight AS score
            FROM photo_embeddings pe
            WHERE pe.project_id = :project_id
              AND pe.caption_embedding IS NOT NULL
        """
        + folder_filter
        +
        """
            ORDER BY pe.caption_embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        ),
        tags AS (
            SELECT pe.photo_id,
                   (1 - (pe.tag_embedding <=> CAST(:query_vector AS vector))) * :tag_weight AS score
            FROM photo_embeddings pe
            WHERE pe.project_id = :project_id
              AND pe.tag_embedding IS NOT NULL
        """
        + folder_filter
        +
        """
            ORDER BY pe.tag_embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        ),
        ocr AS (
            SELECT pe.photo_id,
                   (1 - (pe.ocr_embedding <=> CAST(:query_vector AS vector))) * :ocr_weight AS score
            FROM photo_embeddings pe
            WHERE pe.project_id = :project_id
              AND pe.ocr_embedding IS NOT NULL
        """
        + folder_filter
        +
        """
            ORDER BY pe.ocr_embedding <=> CAST(:query_vector AS vector)
            LIMIT :limit
        )
        SELECT photo_id, MAX(score) AS score
        FROM (
            SELECT * FROM caption
            UNION ALL
            SELECT * FROM tags
            UNION ALL
            SELECT * FROM ocr
        ) s
        GROUP BY photo_id
        ORDER BY score DESC
        LIMIT :limit
        """
    )

    params["caption_weight"] = _VECTOR_FIELD_WEIGHTS["caption_embedding"]
    params["tag_weight"] = _VECTOR_FIELD_WEIGHTS["tag_embedding"]
    params["ocr_weight"] = _VECTOR_FIELD_WEIGHTS["ocr_embedding"]

    rows = db.execute(sql, params).fetchall()
    return {int(r.photo_id): float(r.score) for r in rows}


def _rrf_merge(
    keyword_results: list[SearchCandidate],
    vector_scores: dict[int, float],
) -> list[SearchCandidate]:
    merged: dict[int, SearchCandidate] = {}

    for rank, candidate in enumerate(keyword_results, start=1):
        fused = settings.search_keyword_weight / (settings.search_rrf_k + rank)
        row = merged.get(candidate.photo_id)
        if row is None:
            row = SearchCandidate(photo_id=candidate.photo_id)
            merged[candidate.photo_id] = row
        row.keyword_score = candidate.keyword_score
        row.matched_tags = candidate.matched_tags
        row.final_score = row.final_score + fused

    for rank, (photo_id, vector_score) in enumerate(
        sorted(vector_scores.items(), key=lambda x: x[1], reverse=True),
        start=1,
    ):
        fused = settings.search_vector_weight / (settings.search_rrf_k + rank)
        row = merged.get(photo_id)
        if row is None:
            row = SearchCandidate(photo_id=photo_id)
            merged[photo_id] = row
        row.vector_score = vector_score
        row.final_score = row.final_score + fused

    return sorted(
        merged.values(),
        key=lambda item: item.final_score,
        reverse=True,
    )


def _build_result_items(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    project_id: int | None,
    mode: SearchMode,
    page: int,
    page_size: int,
) -> tuple[int, list[dict]]:
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
        .join(
            PhotoAIAnalysis,
            (PhotoAIAnalysis.photo_id == Photo.id)
            & (PhotoAIAnalysis.project_id == Photo.project_id),
        )
        .filter(Photo.id.in_(photo_ids), Photo.deleted_at.is_(None))
        .all()
    )

    row_by_photo_id = {photo.id: (photo, ai) for photo, ai in rows}
    items: list[dict] = []

    for candidate in page_candidates:
        row = row_by_photo_id.get(candidate.photo_id)
        if row is None:
            continue
        photo, ai = row
        if project_id is not None:
            thumb = (
                f"/api/projects/{project_id}/photos/{photo.id}/thumbnail"
                f"?v={int(photo.updated_at.timestamp()) if photo.updated_at else 0}"
            )
        else:
            thumb = (
                f"/api/photos/{photo.id}/thumbnail"
                f"?v={int(photo.updated_at.timestamp()) if photo.updated_at else 0}"
            )

        if mode == "vector":
            score = candidate.vector_score
        elif mode == "hybrid":
            score = candidate.final_score
        else:
            score = candidate.keyword_score

        items.append(
            {
                "photo_id": photo.id,
                "file_name": photo.file_name,
                "thumbnail_url": thumb,
                "updated_at": photo.updated_at,
                "taken_at": photo.taken_at,
                "width": photo.width,
                "height": photo.height,
                "caption": ai.caption,
                "matched_tags": candidate.matched_tags,
                "score": round(float(score), 6),
            }
        )

    return total, items


def search_photos(
    db: Session,
    query: str,
    page: int = 1,
    page_size: int = 50,
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    mode: SearchMode = "hybrid",
) -> Tuple[int, list]:
    query = query.strip()
    if not query:
        return 0, []

    folder_photo_ids = _resolve_folder_photo_ids(
        db,
        project_id=project_id,
        folder_id=folder_id,
        folder_scope=folder_scope,
    )

    keyword_results = _keyword_search(
        db,
        query,
        project_id=project_id,
        folder_photo_ids=folder_photo_ids,
        limit=settings.search_keyword_top_k,
    )

    if mode == "keyword" or project_id is None:
        return _build_result_items(
            db,
            keyword_results,
            project_id=project_id,
            mode="keyword",
            page=page,
            page_size=page_size,
        )

    vector_scores: dict[int, float] = {}
    try:
        vector_scores = _vector_search(
            db,
            query=query,
            project_id=project_id,
            folder_photo_ids=folder_photo_ids,
            limit=settings.search_vector_top_k,
        )
    except (EmbeddingRequestError, SQLAlchemyError, RuntimeError) as exc:
        logger.warning(
            "Vector search fallback to keyword. project_id=%s query=%s error=%s",
            project_id,
            query,
            exc,
        )
        if mode == "vector":
            return 0, []
        return _build_result_items(
            db,
            keyword_results,
            project_id=project_id,
            mode="keyword",
            page=page,
            page_size=page_size,
        )

    if mode == "vector":
        vector_only = [
            SearchCandidate(photo_id=photo_id, vector_score=score, final_score=score)
            for photo_id, score in sorted(vector_scores.items(), key=lambda x: x[1], reverse=True)
        ]
        return _build_result_items(
            db,
            vector_only,
            project_id=project_id,
            mode="vector",
            page=page,
            page_size=page_size,
        )

    merged = _rrf_merge(keyword_results, vector_scores)
    return _build_result_items(
        db,
        merged,
        project_id=project_id,
        mode="hybrid",
        page=page,
        page_size=page_size,
    )
