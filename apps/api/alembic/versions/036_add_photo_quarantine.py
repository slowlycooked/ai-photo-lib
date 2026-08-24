"""add recoverable photo quarantine

Revision ID: 036_add_photo_quarantine
Revises: 035_search_result_cache_and_indexes
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "036_add_photo_quarantine"
down_revision: Union[str, None] = "035_search_result_cache_and_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_photo_quarantine_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("start_hour", sa.Integer(), server_default="1", nullable=False),
        sa.Column("end_hour", sa.Integer(), server_default="6", nullable=False),
        sa.Column("timezone", sa.Text(), server_default="Asia/Shanghai", nullable=False),
        sa.Column("model_name", sa.Text(), server_default="qwen3.8:27b", nullable=False),
        sa.Column("retention_days", sa.Integer(), server_default="30", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", name="uq_project_photo_quarantine_settings_project"
        ),
    )
    op.create_index(
        "ix_project_photo_quarantine_settings_project_id",
        "project_photo_quarantine_settings",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "photo_quarantine_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="review", nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("preservation_flags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("first_result", sa.JSON(), nullable=False),
        sa.Column("verification_result", sa.JSON(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("quarantine_path", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("previous_photo_status", sa.Text(), nullable=True),
        sa.Column("moved_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("restored_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("deleted_confirmed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "photo_id", name="uq_photo_quarantine_items_project_photo"
        ),
    )
    op.create_index(
        "ix_photo_quarantine_items_project_id",
        "photo_quarantine_items",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_photo_quarantine_items_photo_id",
        "photo_quarantine_items",
        ["photo_id"],
        unique=False,
    )
    op.create_index(
        "ix_photo_quarantine_items_project_status_created",
        "photo_quarantine_items",
        ["project_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_photo_quarantine_items_project_status_created",
        table_name="photo_quarantine_items",
    )
    op.drop_index("ix_photo_quarantine_items_photo_id", table_name="photo_quarantine_items")
    op.drop_index("ix_photo_quarantine_items_project_id", table_name="photo_quarantine_items")
    op.drop_table("photo_quarantine_items")
    op.drop_index(
        "ix_project_photo_quarantine_settings_project_id",
        table_name="project_photo_quarantine_settings",
    )
    op.drop_table("project_photo_quarantine_settings")
