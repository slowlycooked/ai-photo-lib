"""VectorRecallService — multi-field cosine vector search."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy import or_
from sqlalchemy.sql import Select
from sqlalchemy.orm import Session

from ...constants.embedding import DB_EMBEDDING_DIMENSION
from ...config import settings as global_settings
from ...services.embedding_service import EMBEDDING_INPUT_VERSION
from ...services.embedding_client import EmbeddingRequestError, embed_text
from ...models.ai import PhotoEmbedding
from ...services.project_embedding_settings_service import resolve_embedding_settings_strict
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
    folder_photo_subquery: Optional[Select],
    constrained_photo_ids: Optional[set[int]],
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
    if constrained_photo_ids is not None and not constrained_photo_ids:
        return {}, 0

    base_query = db.query(PhotoEmbedding).filter(
        PhotoEmbedding.project_id == project_id,
        getattr(PhotoEmbedding, field_name).is_not(None),
        PhotoEmbedding.embedding_status == "ready",
    )

    if folder_photo_subquery is not None:
        base_query = base_query.filter(PhotoEmbedding.photo_id.in_(folder_photo_subquery))

    if constrained_photo_ids is not None:
        base_query = base_query.filter(PhotoEmbedding.photo_id.in_(constrained_photo_ids))

    stale_count = 0
    if embedding_model and embedding_dimension:
        stale_conditions = [
            PhotoEmbedding.embedding_model.is_distinct_from(embedding_model),
            PhotoEmbedding.embedding_dimension.is_distinct_from(embedding_dimension),
        ]
        if embedding_input_version:
            stale_conditions.append(
                PhotoEmbedding.embedding_input_version.is_distinct_from(embedding_input_version)
            )

        stale_query = db.query(PhotoEmbedding).filter(
            PhotoEmbedding.project_id == project_id,
            getattr(PhotoEmbedding, field_name).is_not(None),
            PhotoEmbedding.embedding_status == "ready",
            or_(*stale_conditions),
        )

        if folder_photo_subquery is not None:
            stale_query = stale_query.filter(PhotoEmbedding.photo_id.in_(folder_photo_subquery))
        if constrained_photo_ids is not None:
            stale_query = stale_query.filter(PhotoEmbedding.photo_id.in_(constrained_photo_ids))
        stale_count = int(stale_query.count() or 0)

    if embedding_model:
        base_query = base_query.filter(PhotoEmbedding.embedding_model == embedding_model)
    if embedding_dimension:
        base_query = base_query.filter(PhotoEmbedding.embedding_dimension == embedding_dimension)
    if embedding_input_version:
        base_query = base_query.filter(PhotoEmbedding.embedding_input_version == embedding_input_version)

    similarity_expr = text(
        f"(1 - (photo_embeddings.{field_name} <=> CAST(:query_vector AS vector))) AS similarity"
    )
    order_expr = text(f"photo_embeddings.{field_name} <=> CAST(:query_vector AS vector)")

    rows = (
        base_query.with_entities(PhotoEmbedding.photo_id, similarity_expr)
        .params(query_vector=query_vector_literal)
        .order_by(order_expr)
        .limit(limit)
        .all()
    )
    return {int(photo_id): float(similarity) for photo_id, similarity in rows}, stale_count


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
        semantic_query_text: str = "",
        is_ocr_query: bool,
        query_intent: str = "",
        recommended_profile: str = "",
        project_id: int,
        folder_photo_subquery: Optional[Select],
        constrained_photo_ids: Optional[set[int]] = None,
        limit: Optional[int] = None,
    ) -> tuple[dict[int, VectorMatchScores], str, str, int]:
        """Return (scores_by_photo_id, embedding_model, fallback_reason, stale_filtered_count)."""
        if global_settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
            raise RuntimeError(
                f"Config mismatch: embedding_dimension must be {_DB_EMBEDDING_DIMENSION}, "
                f"got {global_settings.embedding_dimension}"
            )

        embed_cfg = resolve_embedding_settings_strict(self._db, project_id)
        endpoint_url = embed_cfg["endpoint_url"]
        api_key = embed_cfg["api_key"]
        embedding_model = embed_cfg["model_name"]
        timeout_seconds = embed_cfg["timeout_seconds"]
        input_prefix_query = embed_cfg.get("input_prefix_query")

        embed_input = semantic_query_text.strip() or normalized_query.strip() or query
        if isinstance(input_prefix_query, str) and input_prefix_query.strip():
            embed_input = f"{input_prefix_query.strip()}\n{embed_input}"

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
        is_entity_object_profile = (
            (recommended_profile or "") == "entity_object"
            or (query_intent or "") == "animal_search"
        ) and not is_ocr_query

        if is_entity_object_profile:
            content_top_k = max(5, min(top_k, 15))
            caption_top_k = max(8, min(top_k, 25))
            tag_top_k = max(10, min(top_k, 30))
            ocr_top_k = max(0, min(top_k, 5))
        else:
            content_top_k = top_k
            caption_top_k = top_k
            tag_top_k = top_k
            ocr_top_k = top_k

        content_scores, stale_content = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="content_embedding",
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
            limit=content_top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=EMBEDDING_INPUT_VERSION,
        )
        caption_scores, stale_caption = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="caption_embedding",
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
            limit=caption_top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=EMBEDDING_INPUT_VERSION,
        )
        tag_scores, stale_tag = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="tag_embedding",
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
            limit=tag_top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=EMBEDDING_INPUT_VERSION,
        )
        ocr_scores, stale_ocr = _vector_field_search(
            self._db,
            project_id=project_id,
            query_vector_literal=vector_literal,
            field_name="ocr_embedding",
            folder_photo_subquery=folder_photo_subquery,
            constrained_photo_ids=constrained_photo_ids,
            limit=ocr_top_k,
            embedding_model=embedding_model,
            embedding_dimension=embed_cfg.get("embedding_dimension"),
            embedding_input_version=EMBEDDING_INPUT_VERSION,
        )

        stale_filtered_total = stale_content + stale_caption + stale_tag + stale_ocr

        logger.debug(
            "[vector_recall] field_hits content=%d caption=%d tag=%d ocr=%d top_k=%d profile=%s intent=%s stale_filtered=%d",
            len(content_scores), len(caption_scores), len(tag_scores), len(ocr_scores),
            top_k,
            recommended_profile,
            query_intent,
            stale_filtered_total,
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
