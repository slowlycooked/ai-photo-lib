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
from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from ..services.embedding_client import EmbeddingRequestError, embed_text
from ..services.folder_service import apply_folder_filter
from ..services.project_embedding_settings_service import resolve_embedding_settings
from ..services.query_understanding_service import SearchQueryPlan, understand_query

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

# Default vector field weights: content (semantic composite) gets the highest weight
_DEFAULT_CONTENT_WEIGHT = 0.50
_DEFAULT_TAG_WEIGHT = 0.25
_DEFAULT_CAPTION_WEIGHT = 0.20
_DEFAULT_OCR_WEIGHT = 0.05

# OCR-heavy query overrides
_OCR_CONTENT_WEIGHT = 0.35
_OCR_TAG_WEIGHT = 0.15
_OCR_CAPTION_WEIGHT = 0.10
_OCR_OCR_WEIGHT = 0.40


@dataclass
class VectorMatchScores:
    content_score: float = 0.0
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
    field_scores: dict = field(default_factory=dict)


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

        for fname, weight in (
            ("scene_tags", _WEIGHTS["scene_tags"]),
            ("object_tags", _WEIGHTS["object_tags"]),
            ("activity_tags", _WEIGHTS["activity_tags"]),
            ("search_keywords", _WEIGHTS["search_keywords"]),
            ("quality_tags", _WEIGHTS["quality_tags"]),
            ("location_clues", _WEIGHTS["location_clues"]),
        ):
            tags: list[str] | None = getattr(ai, fname, None)
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
    expanded_terms: list[str],
    *,
    project_id: int | None,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> list[SearchCandidate]:
    # Use expanded terms for matching, fall back to raw tokens from query
    all_terms = expanded_terms if expanded_terms else [t for t in query.split() if t] or [query]

    base_query = (
        db.query(Photo, PhotoAIAnalysis)
        .join(PhotoAIAnalysis, PhotoAIAnalysis.photo_id == Photo.id)
        .filter(Photo.deleted_at.is_(None))
        .filter(_build_any_match_filter(all_terms))
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
        score, matched_tags = _score_result(photo, ai, all_terms)
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
    """Return per-field vector weights for a query.

    content_embedding gets the highest weight by default because it
    encodes the full semantic document. OCR-like queries shift weight
    toward ocr_embedding.
    """
    if _is_ocr_like_query(query):
        return {
            "content_embedding": _OCR_CONTENT_WEIGHT,
            "tag_embedding": _OCR_TAG_WEIGHT,
            "caption_embedding": _OCR_CAPTION_WEIGHT,
            "ocr_embedding": _OCR_OCR_WEIGHT,
        }

    return {
        "content_embedding": _DEFAULT_CONTENT_WEIGHT,
        "tag_embedding": _DEFAULT_TAG_WEIGHT,
        "caption_embedding": _DEFAULT_CAPTION_WEIGHT,
        "ocr_embedding": _DEFAULT_OCR_WEIGHT,
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
    normalized_query: str,
    project_id: int,
    folder_photo_ids: set[int] | None,
    limit: int,
) -> tuple[dict[int, VectorMatchScores], str, str]:
    """Perform multi-field vector search.

    Returns (scores_dict, embedding_model, fallback_reason).
    fallback_reason is empty string when no fallback occurred.
    """
    if settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
        raise RuntimeError(
            f"Config mismatch: embedding_dimension must be {_DB_EMBEDDING_DIMENSION}, "
            f"got {settings.embedding_dimension}"
        )

    # Resolve embedding config from project settings, not AI settings
    try:
        embed_cfg = resolve_embedding_settings(db, project_id)
        endpoint_url = embed_cfg["endpoint_url"]
        api_key = embed_cfg["api_key"]
        embedding_model = embed_cfg["model_name"]
        timeout_seconds = embed_cfg["timeout_seconds"]
    except RuntimeError:
        # Fall back to global config if no project settings found
        endpoint_url = (settings.embedding_base_url or settings.openai_base_url or "").strip()
        api_key = settings.embedding_api_key or settings.openai_api_key
        embedding_model = settings.embedding_model or settings.openai_model
        timeout_seconds = settings.embedding_timeout_seconds

    # Use the semantically expanded/normalised query for embedding
    embed_input = normalized_query if normalized_query.strip() else query

    query_embedding = embed_text(
        embed_input,
        endpoint_url=endpoint_url,
        api_key=api_key,
        model=embedding_model,
        timeout_seconds=timeout_seconds,
        expected_dim=settings.embedding_dimension,
    )
    if should_include_search_trace_payload():
        logger.debug(
            "Search embedding query generated. project_id=%s query=%r normalized=%r "
            "embedding_model=%s dimension=%s",
            project_id,
            query,
            embed_input,
            embedding_model,
            len(query_embedding),
        )

    vector_literal = _query_vector_literal(query_embedding)
    field_weights = _vector_field_weights(query)

    content_scores = _vector_field_search(
        db,
        project_id=project_id,
        query_vector_literal=vector_literal,
        field_name="content_embedding",
        folder_photo_ids=folder_photo_ids,
        limit=limit,
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
    photo_ids = (
        set(content_scores.keys())
        | set(caption_scores.keys())
        | set(tag_scores.keys())
        | set(ocr_scores.keys())
    )
    for photo_id in photo_ids:
        cn = max(0.0, content_scores.get(photo_id, 0.0))
        c = max(0.0, caption_scores.get(photo_id, 0.0))
        t = max(0.0, tag_scores.get(photo_id, 0.0))
        o = max(0.0, ocr_scores.get(photo_id, 0.0))
        total = (
            cn * field_weights["content_embedding"]
            + c * field_weights["caption_embedding"]
            + t * field_weights["tag_embedding"]
            + o * field_weights["ocr_embedding"]
        )
        if total < settings.search_vector_min_score:
            continue
        merged[photo_id] = VectorMatchScores(
            content_score=cn,
            caption_score=c,
            tag_score=t,
            ocr_score=o,
            total_score=total,
        )

    return merged, embedding_model, ""


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

        # Track which fields contributed
        for source_name, score in (
            ("vector_content", vector_match.content_score),
            ("vector_caption", vector_match.caption_score),
            ("vector_tag", vector_match.tag_score),
            ("vector_ocr", vector_match.ocr_score),
        ):
            if score > 0 and source_name not in row.match_source:
                row.match_source.append(source_name)

        row.field_scores = {
            "content": round(vector_match.content_score, 4),
            "caption": round(vector_match.caption_score, 4),
            "tag": round(vector_match.tag_score, 4),
            "ocr": round(vector_match.ocr_score, 4),
        }

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

        item: dict = {
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

        if debug and should_include_search_debug_payload():
            item["keyword_score"] = round(float(candidate.keyword_score), 6)
            item["vector_score"] = round(float(candidate.vector_score), 6)
            item["rrf_score"] = round(float(candidate.rrf_score), 6)
            item["match_source"] = list(candidate.match_source)
            if candidate.field_scores:
                item["field_scores"] = candidate.field_scores

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
) -> Tuple[int, list, Optional[dict]]:
    """Search photos. Returns (total, items, debug_payload).

    debug_payload is None when debug=False or debug is not enabled.
    """
    query = query.strip()
    if not query:
        return 0, [], None

    # Run query understanding to get expanded terms and normalised query
    query_plan: SearchQueryPlan = understand_query(query, project_id=project_id)

    # Respect mode override from caller, but fall back to plan's suggestion
    effective_mode: SearchMode = mode

    logger.debug(
        "Executing search. project_id=%s mode=%s effective_mode=%s page=%s page_size=%s "
        "folder_id=%s folder_scope=%s debug=%s query=%r intent=%s expanded_terms=%s",
        project_id,
        mode,
        effective_mode,
        page,
        page_size,
        folder_id,
        folder_scope,
        debug,
        query,
        query_plan.intent,
        query_plan.expanded_terms[:10],
    )

    folder_photo_ids = _resolve_folder_photo_ids(
        db,
        project_id=project_id,
        folder_id=folder_id,
        folder_scope=folder_scope,
    )

    # Keyword search always uses expanded terms
    keyword_results = _keyword_search(
        db,
        query,
        query_plan.expanded_terms,
        project_id=project_id,
        folder_photo_ids=folder_photo_ids,
        limit=settings.search_keyword_top_k,
    )

    if effective_mode == "keyword" or project_id is None:
        total, items = _build_result_items(
            db,
            keyword_results,
            project_id=project_id,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload: Optional[dict] = None
        if debug and should_include_search_debug_payload():
            debug_payload = _build_debug_payload(
                query_plan=query_plan,
                mode="keyword",
                embedding_model="",
                embedding_dimension=settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason="",
            )
        return total, items, debug_payload

    # Vector / hybrid path
    vector_scores: dict[int, VectorMatchScores] = {}
    embedding_model = ""
    fallback_reason = ""

    try:
        vector_scores, embedding_model, fallback_reason = _vector_search(
            db,
            query=query,
            normalized_query=query_plan.normalized_query,
            project_id=project_id,
            folder_photo_ids=folder_photo_ids,
            limit=settings.search_vector_top_k,
        )
    except (EmbeddingRequestError, SQLAlchemyError, RuntimeError) as exc:
        fallback_reason = str(exc)
        logger.warning(
            "Vector search fallback to keyword. project_id=%s query=%r error=%s",
            project_id,
            query,
            exc,
        )
        # A SQLAlchemyError leaves the session in an aborted-transaction state;
        # rollback so subsequent queries on the same session can proceed.
        if isinstance(exc, SQLAlchemyError):
            try:
                db.rollback()
            except Exception:
                pass
        if effective_mode == "vector":
            debug_payload = None
            if debug and should_include_search_debug_payload():
                debug_payload = _build_debug_payload(
                    query_plan=query_plan,
                    mode="vector",
                    embedding_model=embedding_model,
                    embedding_dimension=settings.embedding_dimension,
                    keyword_candidates=len(keyword_results),
                    vector_candidates=0,
                    merged_candidates=0,
                    fallback_reason=fallback_reason,
                )
            return 0, [], debug_payload
        # hybrid: fall back to keyword-only
        total, items = _build_result_items(
            db,
            keyword_results,
            project_id=project_id,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload = None
        if debug and should_include_search_debug_payload():
            debug_payload = _build_debug_payload(
                query_plan=query_plan,
                mode="hybrid",
                embedding_model=embedding_model,
                embedding_dimension=settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason=fallback_reason,
            )
        return total, items, debug_payload

    if effective_mode == "vector":
        vector_only = [
            SearchCandidate(
                photo_id=photo_id,
                vector_score=scores.total_score,
                final_score=scores.total_score,
                match_source=[
                    source
                    for source, value in (
                        ("vector_content", scores.content_score),
                        ("vector_caption", scores.caption_score),
                        ("vector_tag", scores.tag_score),
                        ("vector_ocr", scores.ocr_score),
                    )
                    if value > 0
                ],
                field_scores={
                    "content": round(scores.content_score, 4),
                    "caption": round(scores.caption_score, 4),
                    "tag": round(scores.tag_score, 4),
                    "ocr": round(scores.ocr_score, 4),
                },
            )
            for photo_id, scores in sorted(
                vector_scores.items(), key=lambda x: x[1].total_score, reverse=True
            )
        ]
        total, items = _build_result_items(
            db,
            vector_only,
            project_id=project_id,
            mode="vector",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload = None
        if debug and should_include_search_debug_payload():
            debug_payload = _build_debug_payload(
                query_plan=query_plan,
                mode="vector",
                embedding_model=embedding_model,
                embedding_dimension=settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=len(vector_scores),
                merged_candidates=len(vector_only),
                fallback_reason="",
            )
        return total, items, debug_payload

    # Hybrid: RRF merge
    merged = _rrf_merge(keyword_results, vector_scores)
    if should_include_search_trace_payload():
        logger.debug(
            "Search scoring summary. project_id=%s query=%r keyword_candidates=%s "
            "vector_candidates=%s merged_candidates=%s",
            project_id,
            query,
            len(keyword_results),
            len(vector_scores),
            len(merged),
        )

    total, items = _build_result_items(
        db,
        merged,
        project_id=project_id,
        mode="hybrid",
        page=page,
        page_size=page_size,
        debug=debug,
    )
    debug_payload = None
    if debug and should_include_search_debug_payload():
        debug_payload = _build_debug_payload(
            query_plan=query_plan,
            mode="hybrid",
            embedding_model=embedding_model,
            embedding_dimension=settings.embedding_dimension,
            keyword_candidates=len(keyword_results),
            vector_candidates=len(vector_scores),
            merged_candidates=len(merged),
            fallback_reason="",
        )
    return total, items, debug_payload


def _build_debug_payload(
    *,
    query_plan: SearchQueryPlan,
    mode: str,
    embedding_model: str,
    embedding_dimension: int,
    keyword_candidates: int,
    vector_candidates: int,
    merged_candidates: int,
    fallback_reason: str,
) -> dict:
    payload: dict = {
        "original_query": query_plan.original_query,
        "normalized_query": query_plan.normalized_query,
        "expanded_terms": query_plan.expanded_terms,
        "intent": query_plan.intent,
        "mode": mode,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "keyword_candidates": keyword_candidates,
        "vector_candidates": vector_candidates,
        "merged_candidates": merged_candidates,
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload
