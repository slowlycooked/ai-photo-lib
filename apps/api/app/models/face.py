from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ProjectFaceSettings(Base):
    """Per-project configuration for local people recognition."""

    __tablename__ = "project_face_settings"
    __table_args__ = (
        sa.UniqueConstraint("project_id", name="uq_project_face_settings_project_id"),
        sa.Index("ix_project_face_settings_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    face_recognition_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    face_provider: Mapped[str] = mapped_column(Text, server_default="opencv", nullable=False)
    face_detector_model: Mapped[str] = mapped_column(Text, server_default="yunet", nullable=False)
    face_embedding_model: Mapped[str] = mapped_column(Text, server_default="sface", nullable=False)
    face_runtime: Mapped[str] = mapped_column(Text, server_default="cpu", nullable=False)
    store_face_crops: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    face_crop_storage: Mapped[str] = mapped_column(Text, server_default="local", nullable=False)
    auto_accept_threshold: Mapped[float] = mapped_column(Float, server_default="0.62", nullable=False)
    review_threshold: Mapped[float] = mapped_column(Float, server_default="0.48", nullable=False)
    cluster_threshold: Mapped[float] = mapped_column(Float, server_default="0.50", nullable=False)
    min_face_size: Mapped[int] = mapped_column(Integer, server_default="40", nullable=False)
    min_detection_confidence: Mapped[float] = mapped_column(
        Float, server_default="0.75", nullable=False
    )
    min_quality_for_prototype: Mapped[float] = mapped_column(
        Float, server_default="0.70", nullable=False
    )
    max_positive_samples_per_person: Mapped[int] = mapped_column(
        Integer, server_default="200", nullable=False
    )
    allow_auto_assignment: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    require_human_confirmation_for_new_person: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    enable_negative_constraints: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    enable_person_cannot_links: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FaceDetection(Base):
    __tablename__ = "face_detections"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "photo_id",
            "bbox_x",
            "bbox_y",
            "bbox_w",
            "bbox_h",
            name="uq_face_detections_project_photo_bbox",
        ),
        sa.Index("ix_face_detections_project_photo", "project_id", "photo_id"),
        sa.Index("ix_face_detections_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    photo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bbox_x: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_w: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_h: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    face_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    face_crop_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    face_crop_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "face_detection_id",
            "model_name",
            "model_version",
            name="uq_face_embeddings_project_detection_model",
        ),
        sa.Index("ix_face_embeddings_project_id", "project_id"),
        sa.Index("ix_face_embeddings_face_detection", "face_detection_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    face_detection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("face_detections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_provider: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_vector: Mapped[Optional[list[float]]] = mapped_column(Vector(), nullable=True)
    embedding_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedded_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (
        sa.Index("ix_persons_project_named", "project_id", "is_named"),
        sa.Index("ix_persons_project_updated_at", "project_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_named: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    representative_face_detection_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("face_detections.id", ondelete="SET NULL"),
        nullable=True,
    )
    sample_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    confirmed_sample_count: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    auto_assigned_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    review_pending_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    created_by: Mapped[str] = mapped_column(Text, server_default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonFaceAssignment(Base):
    __tablename__ = "person_face_assignments"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "person_id",
            "face_detection_id",
            name="uq_person_face_assignments_project_person_face",
        ),
        sa.Index("ix_person_face_assignments_project_person", "project_id", "person_id"),
        sa.Index(
            "ix_person_face_assignments_project_status",
            "project_id",
            "assignment_status",
        ),
        sa.Index("ix_person_face_assignments_face_detection", "face_detection_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    face_detection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("face_detections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignment_status: Mapped[str] = mapped_column(Text, nullable=False)
    assignment_source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    similarity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_positive_sample: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    is_training_candidate: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonPrototype(Base):
    __tablename__ = "person_prototypes"
    __table_args__ = (
        sa.Index("ix_person_prototypes_project_person", "project_id", "person_id"),
        sa.Index(
            "ix_person_prototypes_project_type",
            "project_id",
            "prototype_type",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prototype_type: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[Optional[list[float]]] = mapped_column(Vector(), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    source_assignment_ids: Mapped[Optional[list[int]]] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FaceNegativeConstraint(Base):
    __tablename__ = "face_negative_constraints"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "face_detection_id",
            "not_person_id",
            name="uq_face_negative_constraints_project_face_person",
        ),
        sa.Index("ix_face_negative_constraints_project_face", "project_id", "face_detection_id"),
        sa.Index("ix_face_negative_constraints_project_person", "project_id", "not_person_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    face_detection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("face_detections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    not_person_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class PersonCannotLink(Base):
    __tablename__ = "person_cannot_links"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id",
            "person_id_a",
            "person_id_b",
            name="uq_person_cannot_links_project_pair",
        ),
        sa.Index("ix_person_cannot_links_project_person_a", "project_id", "person_id_a"),
        sa.Index("ix_person_cannot_links_project_person_b", "project_id", "person_id_b"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id_a: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id_b: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
