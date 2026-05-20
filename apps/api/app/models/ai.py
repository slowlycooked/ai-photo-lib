from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PhotoAIAnalysis(Base):
    __tablename__ = "photo_ai_analysis"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "photo_id", name="uq_photo_ai_analysis_project_photo"),
        sa.Index("ix_photo_ai_analysis_project_created_at", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="queued", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("project_prompt_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_model_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parse_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class ProjectPromptTemplate(Base):
    __tablename__ = "project_prompt_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(Text, server_default="image_analysis", nullable=False)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class ProjectAISettings(Base):
    __tablename__ = "project_ai_settings"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["project_id", "active_prompt_template_id"],
            ["project_prompt_templates.project_id", "project_prompt_templates.id"],
            name="fk_project_ai_settings_active_prompt_same_project",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(Text, server_default="llama-server", nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)
    top_p: Mapped[float] = mapped_column(Float, server_default="0.8", nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, server_default="1024", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    output_language: Mapped[str] = mapped_column(Text, server_default="zh-CN", nullable=False)
    json_parse_strategy: Mapped[str] = mapped_column(
        Text, server_default="auto_extract", nullable=False
    )
    active_prompt_template_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
