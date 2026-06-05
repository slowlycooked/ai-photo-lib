from __future__ import annotations

from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, ForeignKey, Text, TIMESTAMP, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.Index("ix_users_role", "role"),
        sa.Index("ix_users_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, server_default="viewer", nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
        sa.Index("ix_project_memberships_project_id", "project_id"),
        sa.Index("ix_project_memberships_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_role: Mapped[str] = mapped_column(Text, server_default="viewer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )


class AIServiceProfile(Base):
    __tablename__ = "ai_service_profiles"
    __table_args__ = (
        sa.Index("ix_ai_service_profiles_capability", "capability"),
        sa.Index("ix_ai_service_profiles_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    capability: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, server_default="openai-compatible", nullable=False)
    endpoint_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_params_json: Mapped[Optional[dict]] = mapped_column(sa.JSON, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(sa.Integer, server_default="60", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    visible_to_projects: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), nullable=False
    )
