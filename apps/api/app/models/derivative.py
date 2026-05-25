from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, ForeignKey, Integer, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class PhotoDerivative(Base):
    """Cached derivative images derived from a source photo.

    Supported kinds:
    - ``ai_thumbnail``    — small JPEG for AI analysis and photo wall display
    - ``face_work_image`` — medium-high resolution JPEG for face detection
    - ``face_crop``       — aligned face crop used for embedding generation
    """

    __tablename__ = "photo_derivatives"
    __table_args__ = (
        # Partial unique index (Postgres) is created in migration 021:
        # UNIQUE (project_id, photo_id, kind) WHERE kind != 'face_crop'
        # Multiple face_crop rows per photo are allowed (one per detected face).
        sa.Index("ix_photo_derivatives_project_photo", "project_id", "photo_id"),
        sa.Index("ix_photo_derivatives_project_kind", "project_id", "kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # One of: ai_thumbnail | face_work_image | face_crop
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    # Absolute path to the cached file
    path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Source fingerprint — used to detect stale cache
    source_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_mtime: Mapped[Optional[float]] = mapped_column(
        sa.Numeric(precision=20, scale=6), nullable=True
    )
    source_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JPEG quality used during generation (nullable for non-JPEG kinds)
    quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ready | failed | missing_source
    status: Mapped[str] = mapped_column(Text, server_default="ready", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # For face_crop: which face_detection produced this crop
    face_detection_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("face_detections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False
    )
