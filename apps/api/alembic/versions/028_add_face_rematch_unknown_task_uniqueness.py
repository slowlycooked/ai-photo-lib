"""add active face rematch unknown task uniqueness

Revision ID: 028_add_face_rematch_unknown_task_uniqueness
Revises: 027_add_face_scan_project_task_uniqueness
Create Date: 2026-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_add_face_rematch_unknown_task_uniqueness"
down_revision: Union[str, None] = "027_add_face_scan_project_task_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_project_tasks_one_active_face_rematch",
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "task_type = 'face_rematch_unknown' AND status IN ('queued', 'running')"
        ),
        postgresql_where=sa.text(
            "task_type = 'face_rematch_unknown' AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_project_tasks_one_active_face_rematch", table_name="project_tasks")
