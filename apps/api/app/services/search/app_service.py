"""SearchService (new package) — the main entry point for photo search.

Orchestrates:
  1. SearchSettingsResolver → EffectiveSearchSettings
  2. understand_query (query understanding)
  3. folder filter resolution
  4. KeywordRecallService
  5. VectorRecallService
  6. RRF fusion
  7. ResultHydrator
  8. DebugPayload builder

For backward compatibility, ``search_photos()`` is also exposed as a
top-level function via ``apps/api/app/services/search_service.py``.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...config import settings as global_settings
from ...logging_config import should_include_search_debug_payload
from ...models.photo import Photo
from ...services.embedding_client import EmbeddingRequestError
from ...services.folder_service import apply_folder_filter
from ...services.query_understanding_service import understand_query
from .debug import build_debug_payload
from .fusion import rrf_merge
from .keyword_recall import KeywordRecallService
from .result_hydrator import build_result_items
from .settings_resolver import SearchSettingsResolver
from .types import EffectiveSearchSettings, SearchCandidate, SearchMode, VectorMatchScores
from .vector_recall import VectorRecallService

logger = logging.getLogger(__name__)


def _resolve_folder_photo_ids(
    db: Session,
    *,
    project_id: int,
    folder_id: Optional[int],
    folder_scope: str,
) -> Optional[set[int]]:
    if folder_id is None:
        return None
    photo_query = db.query(Photo).filter(
        Photo.deleted_at.is_(None), Photo.project_id == project_id
    )
    photo_query = apply_folder_filter(photo_query, db, project_id, folder_id, folder_scope)
    return {p.id for p in photo_query.all()}


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
) -> tuple[int, list, Optional[dict]]:
    """Search photos using project-configurable hybrid search.

    Returns (total, items, debug_payload).
    """
    query = query.strip()
    if not query:
        return 0, [], None

    # Query understanding
    query_plan = understand_query(query, project_id=project_id)

    # Settings resolution
    if project_id is not None:
        effective_settings: EffectiveSearchSettings = SearchSettingsResolver.resolve(
            db, project_id
        )
    else:
        effective_settings = SearchSettingsResolver.defaults()

    # Respect caller's mode override; skip QU mode suggestion here
    effective_mode: SearchMode = mode

    logger.debug(
        "search_photos project_id=%s mode=%s query=%r intent=%s",
        project_id,
        effective_mode,
        query,
        query_plan.intent,
    )

    folder_photo_ids = (
        _resolve_folder_photo_ids(
            db,
            project_id=project_id,
            folder_id=folder_id,
            folder_scope=folder_scope,
        )
        if project_id is not None
        else None
    )

    # Keyword recall (always run — needed for hybrid fallback)
    kw_service = KeywordRecallService(db, effective_settings)
    keyword_results = kw_service.search(
        query_plan,
        project_id=project_id or 0,
        folder_photo_ids=folder_photo_ids,
    )

    # ── Keyword-only mode ─────────────────────────────────────────────────────
    if effective_mode == "keyword" or project_id is None:
        total, items = build_result_items(
            db,
            keyword_results,
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload: Optional[dict] = None
        if debug and should_include_search_debug_payload():
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="keyword",
                embedding_model="",
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason="",
                settings=effective_settings,
            )
        return total, items, debug_payload

    # ── Vector / hybrid path ──────────────────────────────────────────────────
    vector_scores: dict[int, VectorMatchScores] = {}
    embedding_model = ""
    fallback_reason = ""

    is_ocr_query = query_plan.intent == "ocr_text_search"
    vec_service = VectorRecallService(db, effective_settings)

    try:
        vector_scores, embedding_model, fallback_reason = vec_service.search(
            query=query,
            normalized_query=query_plan.normalized_query,
            is_ocr_query=is_ocr_query,
            project_id=project_id,  # type: ignore[arg-type]
            folder_photo_ids=folder_photo_ids,
        )
    except (EmbeddingRequestError, SQLAlchemyError, RuntimeError) as exc:
        fallback_reason = str(exc)
        logger.warning(
            "Vector search fallback to keyword. project_id=%s query=%r error=%s",
            project_id,
            query,
            exc,
        )
        if isinstance(exc, SQLAlchemyError):
            try:
                db.rollback()
            except Exception:
                pass
        if effective_mode == "vector":
            debug_payload = None
            if debug and should_include_search_debug_payload():
                debug_payload = build_debug_payload(
                    query_plan=query_plan,
                    mode="vector",
                    embedding_model=embedding_model,
                    embedding_dimension=global_settings.embedding_dimension,
                    keyword_candidates=len(keyword_results),
                    vector_candidates=0,
                    merged_candidates=0,
                    fallback_reason=fallback_reason,
                    settings=effective_settings,
                )
            return 0, [], debug_payload
        # hybrid falls back to keyword-only
        total, items = build_result_items(
            db,
            keyword_results,
            project_id=project_id or 0,
            mode="keyword",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload = None
        if debug and should_include_search_debug_payload():
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="hybrid",
                embedding_model=embedding_model,
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=0,
                merged_candidates=len(keyword_results),
                fallback_reason=fallback_reason,
                settings=effective_settings,
            )
        return total, items, debug_payload

    # ── Vector-only mode ──────────────────────────────────────────────────────
    if effective_mode == "vector":
        vector_only: list[SearchCandidate] = [
            SearchCandidate(
                photo_id=photo_id,
                vector_score=scores.total_score,
                final_score=scores.total_score,
                match_source=[
                    src
                    for src, val in (
                        ("vector_content", scores.content_score),
                        ("vector_caption", scores.caption_score),
                        ("vector_tag", scores.tag_score),
                        ("vector_ocr", scores.ocr_score),
                    )
                    if val > 0
                ],
                field_scores={
                    "content": round(scores.content_score, 4),
                    "caption": round(scores.caption_score, 4),
                    "tag": round(scores.tag_score, 4),
                    "ocr": round(scores.ocr_score, 4),
                },
                vector_explain={
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
        total, items = build_result_items(
            db,
            vector_only,
            project_id=project_id or 0,
            mode="vector",
            page=page,
            page_size=page_size,
            debug=debug,
        )
        debug_payload = None
        if debug and should_include_search_debug_payload():
            debug_payload = build_debug_payload(
                query_plan=query_plan,
                mode="vector",
                embedding_model=embedding_model,
                embedding_dimension=global_settings.embedding_dimension,
                keyword_candidates=len(keyword_results),
                vector_candidates=len(vector_scores),
                merged_candidates=len(vector_only),
                fallback_reason="",
                settings=effective_settings,
            )
        return total, items, debug_payload

    # ── Hybrid: RRF merge ─────────────────────────────────────────────────────
    merged = rrf_merge(keyword_results, vector_scores, effective_settings)
    total, items = build_result_items(
        db,
        merged,
        project_id=project_id or 0,
        mode="hybrid",
        page=page,
        page_size=page_size,
        debug=debug,
    )
    debug_payload = None
    if debug and should_include_search_debug_payload():
        debug_payload = build_debug_payload(
            query_plan=query_plan,
            mode="hybrid",
            embedding_model=embedding_model,
            embedding_dimension=global_settings.embedding_dimension,
            keyword_candidates=len(keyword_results),
            vector_candidates=len(vector_scores),
            merged_candidates=len(merged),
            fallback_reason="",
            settings=effective_settings,
        )
    return total, items, debug_payload
