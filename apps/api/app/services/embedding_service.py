from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..config import settings
from ..constants.embedding import DB_EMBEDDING_DIMENSION
from ..models.ai import PhotoAIAnalysis, PhotoEmbedding
from .embedding_client import EmbeddingRequestError, embed_texts

if TYPE_CHECKING:
    from ..models.photo import Photo

logger = logging.getLogger(__name__)

_DB_EMBEDDING_DIMENSION = DB_EMBEDDING_DIMENSION

# Version tag written into embedding_input_version.
# Bump this when the document-building logic changes to mark existing
# embeddings as stale so they get rebuilt.
EMBEDDING_INPUT_VERSION = "photo_semantic_qwen3_v2"

_REQUIRED_PHOTO_EMBEDDING_COLUMNS = {
    "id",
    "project_id",
    "photo_id",
    "caption_embedding",
    "tag_embedding",
    "ocr_embedding",
    "content_embedding",
    "caption_text_hash",
    "tag_text_hash",
    "ocr_text_hash",
    "content_text_hash",
    "embedding_model",
    "embedding_dimension",
    "embedding_input_version",
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


def _hash_text(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _apply_input_prefix(value: str | None, prefix: str | None) -> str | None:
    text = _empty_to_none(value)
    if not text:
        return None
    prefix_text = _empty_to_none(prefix)
    if not prefix_text:
        return text
    return f"{prefix_text}\n{text}"


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


def build_photo_embedding_document(
    ai: PhotoAIAnalysis,
    photo: "Photo | None" = None,
) -> str:
    """Build a comprehensive text document representing a photo for embedding.

    Combines caption, tags, OCR text, EXIF data and path information into a
    single string that captures the full semantic content of the photo.
    Empty sections are skipped to avoid noise in the embedding.
    """
    parts: list[str] = []

    caption = _empty_to_none(ai.caption)
    if caption:
        parts.append(f"照片描述：{caption}")

    def _join_tags(values: list | None) -> str | None:
        if not values:
            return None
        items = [v.strip() for v in values if isinstance(v, str) and v.strip()]
        return "\u3001".join(items) if items else None

    scene = _join_tags(ai.scene_tags)
    if scene:
        parts.append(f"场景标签：{scene}")

    objects = _join_tags(ai.object_tags)
    if objects:
        parts.append(f"对象标签：{objects}")

    activities = _join_tags(ai.activity_tags)
    if activities:
        parts.append(f"活动标签：{activities}")

    quality = _join_tags(ai.quality_tags)
    if quality:
        parts.append(f"质量标签：{quality}")

    location = _join_tags(ai.location_clues)
    if location:
        parts.append(f"地点线索：{location}")

    keywords = _join_tags(ai.search_keywords)
    if keywords:
        parts.append(f"搜索关键词：{keywords}")

    ocr = _empty_to_none(ai.ocr_text)
    if ocr:
        parts.append(f"OCR文本：{ocr}")

    if ai.people_count is not None and ai.people_count > 0:
        parts.append(f"人物数量：{ai.people_count}")

    if photo is not None:
        if photo.file_name:
            parts.append(f"文件名：{photo.file_name}")

        relative_path = getattr(photo, "relative_path", None) or getattr(photo, "file_path", None)
        if relative_path:
            parts.append(f"相对路径：{relative_path}")

        if photo.taken_at:
            parts.append(f"拍摄时间：{photo.taken_at.strftime('%Y-%m-%d %H:%M')}")

        camera_make = getattr(photo, "camera_make", None)
        camera_model_attr = getattr(photo, "camera_model", None)
        if camera_make or camera_model_attr:
            camera_info = " ".join(filter(None, [camera_make, camera_model_attr]))
            parts.append(f"相机信息：{camera_info}")

        gps_lat = getattr(photo, "gps_latitude", None)
        gps_lon = getattr(photo, "gps_longitude", None)
        if gps_lat is not None and gps_lon is not None:
            parts.append(f"GPS：{gps_lat:.6f}, {gps_lon:.6f}")

    return "\n\n".join(parts)


def build_embedding_inputs(
    ai: PhotoAIAnalysis,
    photo: "Photo | None" = None,
    *,
    input_prefix_document: str | None = None,
) -> dict[str, str | None]:
    """Return a dict of embedding inputs keyed by field name.

    Returns caption, tags, ocr, and content (the composite document).
    """
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

    content_doc = build_photo_embedding_document(ai, photo)

    return {
        "caption": _apply_input_prefix(ai.caption, input_prefix_document),
        "tags": _apply_input_prefix(";".join(unique_tags), input_prefix_document),
        "ocr": _apply_input_prefix(ai.ocr_text, input_prefix_document),
        "content": _apply_input_prefix(content_doc, input_prefix_document),
    }


def is_embedding_stale(
    ai: PhotoAIAnalysis,
    embedding: PhotoEmbedding | None,
    *,
    model_name: str | None = None,
    dimension: int | None = None,
    photo: "Photo | None" = None,
    input_prefix_document: str | None = None,
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

    # Version check — bump EMBEDDING_INPUT_VERSION to force a rebuild
    current_version = getattr(embedding, "embedding_input_version", None)
    if current_version != EMBEDDING_INPUT_VERSION:
        return True

    inputs = build_embedding_inputs(
        ai,
        photo,
        input_prefix_document=input_prefix_document,
    )
    if (embedding.caption_text_hash or None) != _hash_text(inputs["caption"]):
        return True
    if (embedding.tag_text_hash or None) != _hash_text(inputs["tags"]):
        return True
    if (embedding.ocr_text_hash or None) != _hash_text(inputs["ocr"]):
        return True

    content_hash = _hash_text(inputs["content"])
    current_content_hash = getattr(embedding, "content_text_hash", None)
    if (current_content_hash or None) != content_hash:
        return True

    return False


def upsert_photo_embeddings(
    db: Session,
    *,
    project_id: int,
    photo_id: int,
    ai: PhotoAIAnalysis,
    endpoint_url: str | None = None,
    api_key: str | None = None,
    model_name: str | None = None,
    timeout_seconds: int | None = None,
    photo: "Photo | None" = None,
    input_prefix_document: str | None = None,
) -> PhotoEmbedding:
    _validate_photo_embeddings_schema(db)

    if settings.embedding_dimension != _DB_EMBEDDING_DIMENSION:
        raise RuntimeError(
            "Config mismatch: embedding_dimension must be "
            f"{_DB_EMBEDDING_DIMENSION} for current photo_embeddings schema"
        )

    inputs = build_embedding_inputs(
        ai,
        photo,
        input_prefix_document=input_prefix_document,
    )
    resolved_model = _resolved_embedding_model(model_name)

    caption_hash = _hash_text(inputs["caption"])
    tag_hash = _hash_text(inputs["tags"])
    ocr_hash = _hash_text(inputs["ocr"])
    content_hash = _hash_text(inputs["content"])

    # Build list of (key, text) pairs that are non-empty
    keys: list[str] = []
    texts: list[str] = []
    for key in ("caption", "tags", "ocr", "content"):
        value = inputs.get(key)
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
    if hasattr(row, "content_text_hash"):
        row.content_text_hash = content_hash
    if hasattr(row, "embedding_input_version"):
        row.embedding_input_version = EMBEDDING_INPUT_VERSION

    vectors_by_key: dict[str, list[float]] = {}
    if texts:
        try:
            vectors = embed_texts(
                texts,
                endpoint_url=endpoint_url,
                api_key=api_key,
                model=model_name,
                timeout_seconds=timeout_seconds,
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
    if hasattr(row, "content_embedding"):
        row.content_embedding = vectors_by_key.get("content")
    row.embedding_model = resolved_model
    row.embedding_dimension = settings.embedding_dimension
    row.embedding_status = "ready"
    row.embedding_error = None
    row.embedded_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)

    logger.debug(
        "Upserted photo embeddings. project_id=%s photo_id=%s model=%s "
        "dimension=%s input_version=%s fields=%s",
        project_id,
        photo_id,
        resolved_model,
        settings.embedding_dimension,
        EMBEDDING_INPUT_VERSION,
        keys,
    )

    return row
