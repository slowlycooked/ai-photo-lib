"""add active project task uniqueness

Revision ID: 025_project_task_active_uniqueness
Revises: 024_add_project_tasks
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_project_task_active_uniqueness"
down_revision: Union[str, None] = "024_add_project_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_project_tasks_one_active_scan",
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "task_type IN ('library_scan', 'library_reindex') "
            "AND status IN ('queued', 'running')"
        ),
        postgresql_where=sa.text(
            "task_type IN ('library_scan', 'library_reindex') "
            "AND status IN ('queued', 'running')"
        ),
    )
    op.create_index(
        "uq_project_tasks_one_active_face_cluster",
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "task_type = 'unknown_face_clustering' AND status IN ('queued', 'running')"
        ),
        postgresql_where=sa.text(
            "task_type = 'unknown_face_clustering' AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_project_tasks_one_active_face_cluster", table_name="project_tasks")
    op.drop_index("uq_project_tasks_one_active_scan", table_name="project_tasks")
