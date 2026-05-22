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
) -> dict[int, float]:
    params: dict = {
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
    return {int(row.photo_id): float(row.similarity) for row in rows}


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
    ) -> tuple[dict[int, VectorMatchScores], str, str]:
        """Return (scores_by_photo_id, embedding_model, fallback_reason)."""
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

        content_scores = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="content_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
        )
        caption_scores = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="caption_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
        )
        tag_scores = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="tag_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
        )
        ocr_scores = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="ocr_embedding",
            folder_photo_ids=folder_photo_ids,
            limit=top_k,
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

        return merged, embedding_model, ""
