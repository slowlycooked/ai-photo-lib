from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..config import settings
from ..constants.embedding import DB_EMBEDDING_DIMENSION
from ..models.ai import PhotoAIAnalysis, PhotoEmbedding
from .embedding_client import EmbeddingRequestError, embed_texts

_DB_EMBEDDING_DIMENSION = DB_EMBEDDING_DIMENSION
_REQUIRED_PHOTO_EMBEDDING_COLUMNS = {
    "id",
    "project_id",
    "photo_id",
    "caption_embedding",
    "tag_embedding",
    "ocr_embedding",
    "caption_text_hash",
    "tag_text_hash",
    "ocr_text_hash",
    "embedding_model",
    "embedding_dimension",
    "embedding_status",
    "embedding_error",
    "embedded_at",
    "updated_at",
}


def _empty_to_none(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    return text if text else None


def build_embedding_inputs(ai: PhotoAIAnalysis) -> dict[str, str | None]:
    tag_values: list[str] = []
    for field in (
        "scene_tags",
        "object_tags",
        "activity_tags",
        "quality_tags",
        "location_clues",
        "search_keywords",
    ):
        values = getattr(ai, field, None) or []
        tag_values.extend(v.strip() for v in values if isinstance(v, str) and v.strip())

    unique_tags = list(dict.fromkeys(tag_values))

    return {
        "caption": _empty_to_none(ai.caption),
        "tags": _empty_to_none(";".join(unique_tags)),
        "ocr": _empty_to_none(ai.ocr_text),
    }


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolved_embedding_model(model_name: str | None = None) -> str:
    return model_name or settings.embedding_model or settings.openai_model


def _validate_photo_embeddings_schema(db: Session) -> None:
    """Fail fast with a clear migration hint when schema is outdated."""
    try:
        column_names = {
            column["name"] for column in inspect(db.get_bind()).get_columns("photo_embeddings")
        }
    except Exception:
        # If inspection is unavailable, keep existing behavior and let DB errors surface.
        return

    missing_columns = sorted(_REQUIRED_PHOTO_EMBEDDING_COLUMNS - column_names)
    if missing_columns:
        raise RuntimeError(
            "Incompatible table schema: photo_embeddings is missing required columns "
            f"{missing_columns}. Run DB migrations to head (e.g. alembic upgrade head)."
        )


def is_embedding_stale(
    ai: PhotoAIAnalysis,
    embedding: PhotoEmbedding | None,
    *,
    model_name: str | None = None,
    dimension: int | None = None,
) -> bool:
    if embedding is None:
        return True

    expected_model = _resolved_embedding_model(model_name)
    expected_dimension = dimension or settings.embedding_dimension

    if embedding.embedding_status != "ready":
        return True
    if (embedding.embedding_model or "") != expected_model:
        return True
    if (embedding.embedding_dimension or 0) != expected_dimension:
        return True

    inputs = build_embedding_inputs(ai)
    caption_hash = _hash_text(inputs["caption"])
    tag_hash = _hash_text(inputs["tags"])
    ocr_hash = _hash_text(inputs["ocr"])

    if (embedding.caption_text_hash or None) != caption_hash:
        return True
    if (embedding.tag_text_hash or None) != tag_hash:
        return True
    if (embedding.ocr_text_hash or None) != ocr_hash:
        return True

    return False


def upsert_photo_embeddings(
    db: Session,
    *,
    project_id: int,
    photo_id: int,
    ai: PhotoAIAnalysis,
    endpoint_url: str | None = None,
    model_name: str | None = None,
) -> PhotoEmbedding:
    _validate_photo_embeddings_schema(db)

    if settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
        raise RuntimeError(
            "Config mismatch: embedding_dimension must be "
            f"{_DB_EMBEDDING_DIMENSION} for current photo_embeddings schema"
        )

    inputs = build_embedding_inputs(ai)
    resolved_model = _resolved_embedding_model(model_name)

    caption_hash = _hash_text(inputs["caption"])
    tag_hash = _hash_text(inputs["tags"])
    ocr_hash = _hash_text(inputs["ocr"])

    keys: list[str] = []
    texts: list[str] = []
    for key, value in inputs.items():
        if value:
            keys.append(key)
            texts.append(value)

    row = (
        db.query(PhotoEmbedding)
        .filter(
            PhotoEmbedding.project_id == project_id,
            PhotoEmbedding.photo_id == photo_id,
        )
        .first()
    )
    if not row:
        row = PhotoEmbedding(project_id=project_id, photo_id=photo_id)
        db.add(row)

    row.caption_text_hash = caption_hash
    row.tag_text_hash = tag_hash
    row.ocr_text_hash = ocr_hash

    vectors_by_key: dict[str, list[float]] = {}
    if texts:
        try:
            vectors = embed_texts(
                texts,
                endpoint_url=endpoint_url,
                model=model_name,
                expected_dim=settings.embedding_dimension,
            )
        except EmbeddingRequestError as exc:
            row.embedding_model = resolved_model
            row.embedding_dimension = settings.embedding_dimension
            row.embedding_status = "failed"
            row.embedding_error = str(exc)
            row.updated_at = datetime.now(timezone.utc)
            raise

        if len(keys) != len(vectors):
            raise RuntimeError(
                f"Embedding result mismatch: expected {len(keys)} vectors, got {len(vectors)}"
            )
        vectors_by_key = dict(zip(keys, vectors))

    row.caption_embedding = vectors_by_key.get("caption")
    row.tag_embedding = vectors_by_key.get("tags")
    row.ocr_embedding = vectors_by_key.get("ocr")
    row.embedding_model = resolved_model
    row.embedding_dimension = settings.embedding_dimension
    row.embedding_status = "ready"
    row.embedding_error = None
    row.embedded_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)

    return row
