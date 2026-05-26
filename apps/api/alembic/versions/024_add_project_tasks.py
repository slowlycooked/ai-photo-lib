"""add project tasks table

Revision ID: 024_add_project_tasks
Revises: 023_people_search_indexes
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_add_project_tasks"
down_revision: Union[str, None] = "023_people_search_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TASK_ID_TYPE = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "project_tasks",
        sa.Column("id", _TASK_ID_TYPE, primary_key=True, autoincrement=True),
        sa.Column("project_id", _TASK_ID_TYPE, nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_params", sa.JSON(), nullable=True),
        sa.Column("progress_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_project_tasks_project_created_at",
        "project_tasks",
        ["project_id", "created_at"],
    )
    op.create_index(
        "ix_project_tasks_project_status",
        "project_tasks",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_project_tasks_project_type_status",
        "project_tasks",
        ["project_id", "task_type", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_tasks_project_type_status", table_name="project_tasks")
    op.drop_index("ix_project_tasks_project_status", table_name="project_tasks")
    op.drop_index("ix_project_tasks_project_created_at", table_name="project_tasks")
    op.drop_table("project_tasks")
