from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
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
    semantic_concepts: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
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
    """Project-scoped photo embeddings stored in pgvector columns."""

    __tablename__ = "photo_embeddings"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "photo_id", name="uq_photo_embeddings_project_photo"),
        sa.Index("ix_photo_embeddings_project_id", "project_id"),
        sa.Index("ix_photo_embeddings_project_status", "project_id", "embedding_status"),
        sa.Index(
            "ix_photo_embeddings_project_status_model_dim_version",
            "project_id",
            "embedding_status",
            "embedding_model",
            "embedding_dimension",
            "embedding_input_version",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    photo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    caption_embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)
    tag_embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)
    ocr_embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)
    content_embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(1024), nullable=True)
    caption_text_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tag_text_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_text_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_text_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding_input_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding_status: Mapped[str] = mapped_column(Text, server_default="ready", nullable=False)
    embedding_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class ProjectEmbeddingSettings(Base):
    """Per-project configuration for the text embedding service."""

    __tablename__ = "project_embedding_settings"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            name="uq_project_embedding_settings_project_id",
        ),
        sa.Index("ix_project_embedding_settings_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_service_profile_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("ai_service_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        Text, server_default="openai-compatible", nullable=False
    )
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(
        Integer, server_default="1024", nullable=False
    )
    batch_size: Mapped[int] = mapped_column(Integer, server_default="16", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default="60", nullable=False)
    input_prefix_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_prefix_document: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    search_content_vector_weight: Mapped[float] = mapped_column(
        Float, server_default="0.5", nullable=False
    )
    search_tag_vector_weight: Mapped[float] = mapped_column(
        Float, server_default="0.25", nullable=False
    )
    search_caption_vector_weight: Mapped[float] = mapped_column(
        Float, server_default="0.2", nullable=False
    )
    search_ocr_vector_weight: Mapped[float] = mapped_column(
        Float, server_default="0.05", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class ProjectQueryPlannerSettings(Base):
    """Per-project configuration for LLM query planner runtime."""

    __tablename__ = "project_query_planner_settings"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            name="uq_project_query_planner_settings_project_id",
        ),
        sa.Index("ix_project_query_planner_settings_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_service_profile_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("ai_service_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    provider: Mapped[str] = mapped_column(Text, server_default="llama-server", nullable=False)
    endpoint_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)
    top_p: Mapped[float] = mapped_column(Float, server_default="0.8", nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, server_default="700", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default="20", nullable=False)
    json_parse_strategy: Mapped[str] = mapped_column(
        Text,
        server_default="strict_json_then_extract",
        nullable=False,
    )
    planner_version: Mapped[str] = mapped_column(
        Text,
        server_default="llm_query_planner_v1",
        nullable=False,
    )
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fallback_mode: Mapped[str] = mapped_column(
        Text,
        server_default="rule_fallback",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
    )


class AIJob(Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        sa.Index("ix_ai_jobs_status_created_at", "status", "created_at"),
        sa.Index("ix_ai_jobs_status_lease_expires_at", "status", "lease_expires_at"),
    )

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
    locked_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
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
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_project_prompt_templates_project_id_id",
        ),
    )

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
    ai_service_profile_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("ai_service_profiles.id", ondelete="SET NULL"),
        nullable=True,
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
