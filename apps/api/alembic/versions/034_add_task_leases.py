"""add task lease and heartbeat fields

Revision ID: 034_add_task_leases
Revises: 033_repair_project_task_active_indexes
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_add_task_leases"
down_revision: Union[str, None] = "033_repair_project_task_active_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_lease_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column("locked_by", sa.Text(), nullable=True))
    op.add_column(table_name, sa.Column("locked_at", sa.TIMESTAMP(), nullable=True))
    op.add_column(table_name, sa.Column("heartbeat_at", sa.TIMESTAMP(), nullable=True))
    op.add_column(table_name, sa.Column("lease_expires_at", sa.TIMESTAMP(), nullable=True))
    op.add_column(table_name, sa.Column("last_error_code", sa.Text(), nullable=True))
    op.add_column(table_name, sa.Column("last_error_at", sa.TIMESTAMP(), nullable=True))


def _drop_lease_columns(table_name: str) -> None:
    op.drop_column(table_name, "last_error_at")
    op.drop_column(table_name, "last_error_code")
    op.drop_column(table_name, "lease_expires_at")
    op.drop_column(table_name, "heartbeat_at")
    op.drop_column(table_name, "locked_at")
    op.drop_column(table_name, "locked_by")


def upgrade() -> None:
    _add_lease_columns("project_tasks")
    _add_lease_columns("ai_jobs")

    op.create_index(
        "ix_project_tasks_status_created_at",
        "project_tasks",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_project_tasks_status_lease_expires_at",
        "project_tasks",
        ["status", "lease_expires_at"],
    )
    op.create_index(
        "ix_ai_jobs_status_created_at",
        "ai_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_ai_jobs_status_lease_expires_at",
        "ai_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_status_lease_expires_at", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_status_created_at", table_name="ai_jobs")
    op.drop_index("ix_project_tasks_status_lease_expires_at", table_name="project_tasks")
    op.drop_index("ix_project_tasks_status_created_at", table_name="project_tasks")

    _drop_lease_columns("ai_jobs")
    _drop_lease_columns("project_tasks")
