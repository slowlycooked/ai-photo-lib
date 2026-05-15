from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PhotoAIAnalysis(Base):
    __tablename__ = "photo_ai_analysis"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scene_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    object_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    activity_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    quality_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    location_clues: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    search_keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    people_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class PhotoEmbedding(Base):
    """Placeholder model for future pgvector embeddings (v0.4+).

    The three embedding columns are stored as JSON-serialised TEXT for now.
    They will be migrated to the native `vector(1024)` type in v0.4.
    """

    __tablename__ = "photo_embeddings"

    photo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    caption_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tag_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    photo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="queued", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
