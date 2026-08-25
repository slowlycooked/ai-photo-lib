from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Integer, JSON, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

_TASK_ID_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class ProjectTask(Base):
    __tablename__ = "project_tasks"
    __table_args__ = (
        sa.Index("ix_project_tasks_project_created_at", "project_id", "created_at"),
        sa.Index("ix_project_tasks_project_status", "project_id", "status"),
        sa.Index("ix_project_tasks_project_type_status", "project_id", "task_type", "status"),
        sa.Index("ix_project_tasks_status_created_at", "status", "created_at"),
        sa.Index("ix_project_tasks_status_lease_expires_at", "status", "lease_expires_at"),
        sa.Index(
            "uq_project_tasks_one_active_scan",
            "project_id",
            unique=True,
            sqlite_where=sa.text(
                "task_type IN ('library_scan', 'library_reindex') "
                "AND status IN ('queued', 'running')"
            ),
            postgresql_where=sa.text(
                "task_type IN ('library_scan', 'library_reindex') "
                "AND status IN ('queued', 'running')"
            ),
        ),
        sa.Index(
            "uq_project_tasks_one_active_face_cluster",
            "project_id",
            unique=True,
            sqlite_where=sa.text(
                "task_type = 'unknown_face_clustering' AND status IN ('queued', 'running')"
            ),
            postgresql_where=sa.text(
                "task_type = 'unknown_face_clustering' AND status IN ('queued', 'running')"
            ),
        ),
        sa.Index(
            "uq_project_tasks_one_active_face_scan",
            "project_id",
            unique=True,
            sqlite_where=sa.text(
                "task_type = 'face_scan_project' AND status IN ('queued', 'running')"
            ),
            postgresql_where=sa.text(
                "task_type = 'face_scan_project' AND status IN ('queued', 'running')"
            ),
        ),
        sa.Index(
            "uq_project_tasks_one_active_photo_quarantine",
            "project_id",
            unique=True,
            sqlite_where=sa.text(
                "task_type = 'photo_quarantine_analysis' AND status IN ('queued', 'running')"
            ),
            postgresql_where=sa.text(
                "task_type = 'photo_quarantine_analysis' AND status IN ('queued', 'running')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(_TASK_ID_TYPE, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        _TASK_ID_TYPE,
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="queued", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    request_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    progress_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
