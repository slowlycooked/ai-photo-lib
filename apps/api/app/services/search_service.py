from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

from sqlalchemy import func, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..constants.embedding import DB_EMBEDDING_DIMENSION
from ..logging_config import (
    should_include_search_debug_payload,
    should_include_search_trace_payload,
)
from ..models.ai import PhotoAIAnalysis, ProjectAISettings
from ..models.photo import Photo
from ..services.embedding_client import EmbeddingRequestError, embed_text
from ..services.folder_service import apply_folder_filter

logger = logging.getLogger(__name__)

SearchMode = Literal["keyword", "vector", "hybrid"]

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
_DB_EMBEDDING_DIMENSION = DB_EMBEDDING_DIMENSION


@dataclass
class VectorMatchScores:
    caption_score: float = 0.0
    tag_score: float = 0.0
    ocr_score: float = 0.0
    total_score: float = 0.0


@dataclass
class SearchCandidate:
    photo_id: int
    keyword_score: float = 0.0
    vector_score: float = 0.0
    final_score: float = 0.0
    rrf_score: float = 0.0
    matched_tags: list[str] = field(default_factory=list)
    match_source: list[str] = field(default_factory=list)


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
                match_source=["keyword"],
            )
        )

    candidates.sort(key=lambda item: item.keyword_score, reverse=True)
    return candidates


def _query_vector_literal(query_vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"


def _is_ocr_like_query(query: str) -> bool:
    has_order_token = bool(re.search(r"(order|invoice|id|sn|单号|订单|发票|金额)", query, flags=re.IGNORECASE))
    digit_count = sum(1 for ch in query if ch.isdigit())
    ascii_count = sum(1 for ch in query if ch.isascii() and ch.isalnum())
    return has_order_token or digit_count >= 4 or ascii_count >= max(6, len(query) // 2)


def _vector_field_weights(query: str) -> dict[str, float]:
    caption_weight = settings.search_caption_vector_weight
    tag_weight = settings.search_tag_vector_weight
    ocr_weight = settings.search_ocr_vector_weight

    if _is_ocr_like_query(query):
        ocr_weight = ocr_weight + 0.2

    total = caption_weight + tag_weight + ocr_weight
    if total <= 0:
        return {
            "caption_embedding": 0.35,
            "tag_embedding": 0.50,
            "ocr_embedding": 0.15,
        }

    return {
        "caption_embedding": caption_weight / total,
        "tag_embedding": tag_weight / total,
        "ocr_embedding": ocr_weight / total,
    }


def _vector_field_search(
    db: Session,
    *,
    project_id: int,
    query_vector_literal: str,
    field_name: str,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> dict[int, float]:
    params: dict[str, object] = {
        "project_id": project_id,
        "query_vector": query_vector_literal,
        "limit": limit,
    }
    folder_filter = ""
    if folder_photo_ids is not None:
        if not folder_photo_ids:
            return {}
        params["photo_ids"] = list(folder_photo_ids)
        folder_filter = " AND pe.photo_id = ANY(:photo_ids)"

    sql = text(
        f"""
        SELECT pe.photo_id,
               (1 - (pe.{field_name} <=> CAST(:query_vector AS vector))) AS similarity
        FROM photo_embeddings pe
        WHERE pe.project_id = :project_id
          AND pe.{field_name} IS NOT NULL
          {folder_filter}
        ORDER BY pe.{field_name} <=> CAST(:query_vector AS vector)
        LIMIT :limit
        """
    )
    rows = db.execute(sql, params).fetchall()
    result: dict[int, float] = {}
    for row in rows:
        result[int(row.photo_id)] = float(row.similarity)
    return result


def _vector_search(
    db: Session,
    *,
    query: str,
    project_id: int,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> dict[int, VectorMatchScores]:
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
    embedding_model = settings.embedding_model or (settings_row.model_name if settings_row else "") or settings.openai_model

    query_embedding = embed_text(
        query,
        endpoint_url=endpoint_url,
        model=embedding_model,
        expected_dim=settings.embedding_dimension,
    )
    if should_include_search_trace_payload():
        logger.trace(
            "Search embedding query generated. project_id=%s query=%s embedding_model=%s dimension=%s",
            project_id,
            query,
            embedding_model,
            len(query_embedding),
        )

    vector_literal = _query_vector_literal(query_embedding)
    field_weights = _vector_field_weights(query)
    if should_include_search_trace_payload():
        logger.trace(
            "Search vector weights. project_id=%s query=%s field_weights=%s",
            project_id,
            query,
            field_weights,
        )

    caption_scores = _vector_field_search(
        db,
        project_id=project_id,
        query_vector_literal=vector_literal,
        field_name="caption_embedding",
        folder_photo_ids=folder_photo_ids,
        limit=limit,
    )
    tag_scores = _vector_field_search(
        db,
        project_id=project_id,
        query_vector_literal=vector_literal,
        field_name="tag_embedding",
        folder_photo_ids=folder_photo_ids,
        limit=limit,
    )
    ocr_scores = _vector_field_search(
        db,
        project_id=project_id,
        query_vector_literal=vector_literal,
        field_name="ocr_embedding",
        folder_photo_ids=folder_photo_ids,
        limit=limit,
    )

    merged: dict[int, VectorMatchScores] = {}
    photo_ids = set(caption_scores.keys()) | set(tag_scores.keys()) | set(ocr_scores.keys())
    for photo_id in photo_ids:
        c = max(0.0, caption_scores.get(photo_id, 0.0))
        t = max(0.0, tag_scores.get(photo_id, 0.0))
        o = max(0.0, ocr_scores.get(photo_id, 0.0))
        total = (
            c * field_weights["caption_embedding"]
            + t * field_weights["tag_embedding"]
            + o * field_weights["ocr_embedding"]
        )
        if total < settings.search_vector_min_score:
            continue
        merged[photo_id] = VectorMatchScores(
            caption_score=c,
            tag_score=t,
            ocr_score=o,
            total_score=total,
        )

    return merged


def _rrf_merge(
    keyword_results: list[SearchCandidate],
    vector_scores: dict[int, VectorMatchScores],
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
        row.rrf_score += fused
        row.final_score = row.rrf_score
        if "keyword" not in row.match_source:
            row.match_source.append("keyword")

    for rank, (photo_id, vector_match) in enumerate(
        sorted(vector_scores.items(), key=lambda x: x[1].total_score, reverse=True),
        start=1,
    ):
        fused = settings.search_vector_weight / (settings.search_rrf_k + rank)
        row = merged.get(photo_id)
        if row is None:
            row = SearchCandidate(photo_id=photo_id)
            merged[photo_id] = row
        row.vector_score = vector_match.total_score
        row.rrf_score += fused
        row.final_score = row.rrf_score
        for source_name, score in (
            ("vector_caption", vector_match.caption_score),
            ("vector_tag", vector_match.tag_score),
            ("vector_ocr", vector_match.ocr_score),
        ):
            if score > 0 and source_name not in row.match_source:
                row.match_source.append(source_name)

    return sorted(merged.values(), key=lambda item: item.final_score, reverse=True)


def _build_result_items(
    db: Session,
    candidates: list[SearchCandidate],
    *,
    project_id: int | None,
    mode: SearchMode,
    page: int,
    page_size: int,
    debug: bool,
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

        item = {
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

        if debug and settings.search_debug_enabled and should_include_search_debug_payload():
            item["keyword_score"] = round(float(candidate.keyword_score), 6)
            item["vector_score"] = round(float(candidate.vector_score), 6)
            item["rrf_score"] = round(float(candidate.rrf_score), 6)
            item["match_source"] = list(candidate.match_source)

        items.append(item)

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
    debug: bool = False,
) -> Tuple[int, list]:
    query = query.strip()
    if not query:
        return 0, []

    logger.debug(
        "Executing search. project_id=%s mode=%s page=%s page_size=%s folder_id=%s folder_scope=%s debug=%s query=%s",
        project_id,
        mode,
        page,
        page_size,
        folder_id,
        folder_scope,
        debug,
        query,
    )

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
            debug=debug,
        )

    vector_scores: dict[int, VectorMatchScores] = {}
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
            debug=debug,
        )

    if mode == "vector":
        vector_only = [
            SearchCandidate(
                photo_id=photo_id,
                vector_score=scores.total_score,
                final_score=scores.total_score,
                match_source=[
                    source
                    for source, value in (
                        ("vector_caption", scores.caption_score),
                        ("vector_tag", scores.tag_score),
                        ("vector_ocr", scores.ocr_score),
                    )
                    if value > 0
                ],
            )
            for photo_id, scores in sorted(vector_scores.items(), key=lambda x: x[1].total_score, reverse=True)
        ]
        return _build_result_items(
            db,
            vector_only,
            project_id=project_id,
            mode="vector",
            page=page,
            page_size=page_size,
            debug=debug,
        )

    merged = _rrf_merge(keyword_results, vector_scores)
    if should_include_search_trace_payload():
        logger.trace(
            "Search scoring summary. project_id=%s query=%s keyword_candidates=%s vector_candidates=%s merged_candidates=%s",
            project_id,
            query,
            len(keyword_results),
            len(vector_scores),
            len(merged),
        )
    return _build_result_items(
        db,
        merged,
        project_id=project_id,
        mode="hybrid",
        page=page,
        page_size=page_size,
        debug=debug,
    )
