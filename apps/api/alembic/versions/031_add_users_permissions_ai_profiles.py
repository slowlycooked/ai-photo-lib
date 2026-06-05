"""add users permissions ai profiles

Revision ID: 031_users_permissions_ai_profiles
Revises: 030_qp_enabled_default_true
Create Date: 2026-06-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031_users_permissions_ai_profiles"
down_revision: Union[str, None] = "030_qp_enabled_default_true"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), server_default="viewer", nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_status", "users", ["status"])

    op.create_table(
        "project_memberships",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("project_role", sa.Text(), server_default="viewer", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
    )
    op.create_index("ix_project_memberships_project_id", "project_memberships", ["project_id"])
    op.create_index("ix_project_memberships_user_id", "project_memberships", ["user_id"])

    op.create_table(
        "ai_service_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("capability", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), server_default="openai-compatible", nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("model_params_json", sa.JSON(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("visible_to_projects", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_service_profiles_capability", "ai_service_profiles", ["capability"])
    op.create_index("ix_ai_service_profiles_enabled", "ai_service_profiles", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_ai_service_profiles_enabled", table_name="ai_service_profiles")
    op.drop_index("ix_ai_service_profiles_capability", table_name="ai_service_profiles")
    op.drop_table("ai_service_profiles")
    op.drop_index("ix_project_memberships_user_id", table_name="project_memberships")
    op.drop_index("ix_project_memberships_project_id", table_name="project_memberships")
    op.drop_table("project_memberships")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")
