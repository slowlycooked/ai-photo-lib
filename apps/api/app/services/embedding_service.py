from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import PhotoAIAnalysis, PhotoEmbedding
from .embedding_client import embed_texts

_DB_EMBEDDING_DIMENSION = 1024


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


def upsert_photo_embeddings(
    db: Session,
    *,
    project_id: int,
    photo_id: int,
    ai: PhotoAIAnalysis,
    endpoint_url: str | None = None,
    model_name: str | None = None,
) -> PhotoEmbedding:
    if settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
        raise RuntimeError(
            "Config mismatch: embedding_dimension must be "
            f"{_DB_EMBEDDING_DIMENSION} for current photo_embeddings schema"
        )

    inputs = build_embedding_inputs(ai)

    keys: list[str] = []
    texts: list[str] = []
    for key, value in inputs.items():
        if value:
            keys.append(key)
            texts.append(value)

    vectors_by_key: dict[str, list[float]] = {}
    if texts:
        vectors = embed_texts(
            texts,
            endpoint_url=endpoint_url,
            model=model_name,
            expected_dim=settings.embedding_dimension,
        )
        if len(keys) != len(vectors):
            raise RuntimeError(
                f"Embedding result mismatch: expected {len(keys)} vectors, got {len(vectors)}"
            )
        vectors_by_key = dict(zip(keys, vectors))

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

    row.caption_embedding = vectors_by_key.get("caption")
    row.tag_embedding = vectors_by_key.get("tags")
    row.ocr_embedding = vectors_by_key.get("ocr")
    row.embedding_model = model_name or settings.embedding_model or settings.openai_model
    row.updated_at = datetime.now(timezone.utc)
    return row
