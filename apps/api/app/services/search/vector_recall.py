"""VectorRecallService — multi-field cosine vector search."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...constants.embedding import DB_EMBEDDING_DIMENSION
from ...config import settings as global_settings
from ...services.embedding_client import EmbeddingRequestError, embed_text
from ...services.project_embedding_settings_service import resolve_embedding_settings
from .types import (
    DEFAULT_OCR_VECTOR_FIELD_WEIGHTS,
    DEFAULT_VECTOR_FIELD_WEIGHTS,
    EffectiveSearchSettings,
    SearchCandidate,
    VectorMatchScores,
)

logger = logging.getLogger(__name__)

_DB_EMBEDDING_DIMENSION = DB_EMBEDDING_DIMENSION


def _query_vector_literal(query_vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in query_vector) + "]"


def _vector_field_search(
    db: Session,
    *,
    project_id: int,
    query_vector_literal: str,
    field_name: str,
    folder_photo_ids: Optional[set[int]],
    limit: int,
    embedding_model: Optional[str] = None,
    embedding_dimension: Optional[int] = None,
    embedding_input_version: Optional[str] = None,
) -> tuple[dict[int, float], int]:
    """Return (scores_dict, stale_filtered_count).

    Only rows with embedding_status='ready' are considered.
    If embedding_model / embedding_dimension / embedding_input_version are
    provided, rows that don't match are also excluded (stale-filtered).
    """
    params: dict = {
        "project_id": project_id,
        "query_vector": query_vector_literal,
        "limit": limit,
    }
    folder_filter = ""
    if folder_photo_ids is not None:
        if not folder_photo_ids:
            return {}, 0
        params["photo_ids"] = list(folder_photo_ids)
        folder_filter = " AND pe.photo_id = ANY(:photo_ids)"

    # Build optional stale-model filters
    stale_filters = " AND pe.embedding_status = 'ready'"
    if embedding_model:
        params["embedding_model"] = embedding_model
        stale_filters += " AND pe.embedding_model = :embedding_model"
    if embedding_dimension:
        params["embedding_dimension"] = embedding_dimension
        stale_filters += " AND pe.embedding_dimension = :embedding_dimension"
    if embedding_input_version:
        params["embedding_input_version"] = embedding_input_version
        stale_filters += " AND pe.embedding_input_version = :embedding_input_version"

    # Count how many rows would be included without stale-model filter
    # (used for stale_filtered debug stat — approximate: only when all filters provided)
    stale_count = 0
    if embedding_model and embedding_dimension:
        count_sql = text(
            f"""
            SELECT COUNT(*) AS cnt
            FROM photo_embeddings pe
            WHERE pe.project_id = :project_id
              AND pe.{field_name} IS NOT NULL
              {folder_filter}
              AND pe.embedding_status = 'ready'
              AND (
                pe.embedding_model IS DISTINCT FROM :embedding_model
                OR pe.embedding_dimension IS DISTINCT FROM :embedding_dimension
              )
            """
        )
        count_params = {k: params[k] for k in params if k != "limit"}
        result = db.execute(count_sql, count_params).scalar()
        stale_count = int(result or 0)

    sql = text(
        f"""
        SELECT pe.photo_id,
               (1 - (pe.{field_name} <=> CAST(:query_vector AS vector))) AS similarity
        FROM photo_embeddings pe
        WHERE pe.project_id = :project_id
          AND pe.{field_name} IS NOT NULL
          {folder_filter}
          {stale_filters}
        ORDER BY pe.{field_name} <=> CAST(:query_vector AS vector)
        LIMIT :limit
        """
    )
    rows = db.execute(sql, params).fetchall()
    return {int(row.photo_id): float(row.similarity) for row in rows}, stale_count


class VectorRecallService:
    """Embed a query and return multi-field cosine similarity scores."""

    def __init__(self, db: Session, search_settings: EffectiveSearchSettings) -> None:
        self._db = db
        self._settings = search_settings

    def search(
        self,
        *,
        query: str,
        normalized_query: str,
        is_ocr_query: bool,
        project_id: int,
        folder_photo_ids: Optional[set[int]],
        limit: Optional[int] = None,
    ) -> tuple[dict[int, VectorMatchScores], str, str, int]:
        """Return (scores_by_photo_id, embedding_model, fallback_reason, stale_filtered_count)."""
        if global_settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Config mismatch: embedding_dimension must be {_DB_EMBEDDING_DIMENSION}, "
                f"got {global_settings.embedding_dimension}"
            )

        try:
            embed_cfg = resolve_embedding_settings(self._db, project_id)
            endpoint_url = embed_cfg["endpoint_url"]
            api_key = embed_cfg["api_key"]
            embedding_model = embed_cfg["model_name"]
            timeout_seconds = embed_cfg["timeout_seconds"]
        except RuntimeError:
            endpoint_url = (
                global_settings.embedding_base_url or global_settings.openai_base_url or ""
            ).strip()
            api_key = global_settings.embedding_api_key or global_settings.openai_api_key
            embedding_model = global_settings.embedding_model or global_settings.openai_model
            timeout_seconds = global_settings.embedding_timeout_seconds
            embed_cfg = {}

        embed_input = normalized_query if normalized_query.strip() else query

        logger.debug(
            "[vector_recall] embed_text model=%s input=%r endpoint=%s",
            embedding_model,
            embed_input,
            endpoint_url,
        )

        query_embedding = embed_text(
            embed_input,
            endpoint_url=endpoint_url,
            api_key=api_key,
            model=embedding_model,
            timeout_seconds=timeout_seconds,
            expected_dim=global_settings.embedding_dimension,
        )

        vector_literal = _query_vector_literal(query_embedding)

        # Choose field weights: OCR path or normal path
        if is_ocr_query:
            field_weights = self._settings.ocr_vector_field_weights
        else:
            field_weights = self._settings.vector_field_weights

        top_k = limit if limit is not None else self._settings.vector_top_k

        content_scores, stale_content = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="content_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=embed_cfg.get("embedding_input_version"),
        )
        caption_scores, stale_caption = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="caption_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=embed_cfg.get("embedding_input_version"),
        )
        tag_scores, stale_tag = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="tag_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=embed_cfg.get("embedding_input_version"),
        )
        ocr_scores, stale_ocr = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="ocr_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=embed_cfg.get("embedding_input_version"),
        )

        stale_filtered_total = stale_content + stale_caption + stale_tag + stale_ocr

        logger.debug(
            "[vector_recall] field_hits content=%d caption=%d tag=%d ocr=%d top_k=%d stale_filtered=%d",
            len(content_scores), len(caption_scores), len(tag_scores), len(ocr_scores),
            top_k, stale_filtered_total,
        )

        all_photo_ids = (
            set(content_scores) | set(caption_scores) | set(tag_scores) | set(ocr_scores)
        )
        merged: dict[int, VectorMatchScores] = {}
        for photo_id in all_photo_ids:
            cn = max(0.0, content_scores.get(photo_id, 0.0))
            cp = max(0.0, caption_scores.get(photo_id, 0.0))
            tg = max(0.0, tag_scores.get(photo_id, 0.0))
            oc = max(0.0, ocr_scores.get(photo_id, 0.0))
            total = (
                cn * field_weights.get("content_embedding", 0.5)
                + cp * field_weights.get("caption_embedding", 0.2)
                + tg * field_weights.get("tag_embedding", 0.25)
                + oc * field_weights.get("ocr_embedding", 0.05)
            )
            if total < self._settings.vector_min_score:
                continue
            merged[photo_id] = VectorMatchScores(
                content_score=cn,
                caption_score=cp,
                tag_score=tg,
                ocr_score=oc,
                total_score=total,
            )

        logger.debug(
            "[vector_recall] done candidates=%d (after min_score=%.4f filter, union=%d)",
            len(merged), self._settings.vector_min_score, len(all_photo_ids),
        )
        if merged and logger.isEnabledFor(5):  # TRACE level
            top = sorted(merged.items(), key=lambda x: x[1].total_score, reverse=True)[:10]
            for pid, scores in top:
                logger.log(
                    5,
                    "[vector_recall] photo_id=%d total=%.4f content=%.4f caption=%.4f tag=%.4f ocr=%.4f",
                    pid, scores.total_score, scores.content_score,
                    scores.caption_score, scores.tag_score, scores.ocr_score,
                )

        return merged, embedding_model, "", stale_filtered_total
