from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class ProjectPhotoQuarantineSettings(Base):
    __tablename__ = "project_photo_quarantine_settings"
    __table_args__ = (
        sa.UniqueConstraint("project_id", name="uq_project_photo_quarantine_settings_project"),
    )

    id: Mapped[int] = mapped_column(_ID_TYPE, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        _ID_TYPE,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    start_hour: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    end_hour: Mapped[int] = mapped_column(Integer, server_default="6", nullable=False)
    timezone: Mapped[str] = mapped_column(
        Text, server_default="Asia/Shanghai", nullable=False
    )
    model_name: Mapped[str] = mapped_column(
        Text, server_default="qwen3.8:27b", nullable=False
    )
    retention_days: Mapped[int] = mapped_column(Integer, server_default="30", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class PhotoQuarantineItem(Base):
    __tablename__ = "photo_quarantine_items"
    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "photo_id", name="uq_photo_quarantine_items_project_photo"
        ),
        sa.Index(
            "ix_photo_quarantine_items_project_status_created",
            "project_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(_ID_TYPE, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        _ID_TYPE,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_id: Mapped[int] = mapped_column(
        _ID_TYPE,
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(Text, server_default="review", nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, server_default="0", nullable=False)
    reason: Mapped[str] = mapped_column(Text, server_default="", nullable=False)
    preservation_flags: Mapped[list] = mapped_column(JSON, server_default="[]", nullable=False)
    first_result: Mapped[dict] = mapped_column(JSON, nullable=False)
    verification_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    quarantine_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    previous_photo_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    moved_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    restored_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    deleted_confirmed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    human_label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_label_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_labeled_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_labeled_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
