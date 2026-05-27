"""add active face scan project task uniqueness

Revision ID: 027_add_face_scan_project_task_uniqueness
Revises: 026_add_semantic_concepts
Create Date: 2026-05-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_add_face_scan_project_task_uniqueness"
down_revision: Union[str, None] = "026_add_semantic_concepts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_project_tasks_one_active_face_scan",
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "task_type = 'face_scan_project' AND status IN ('queued', 'running')"
        ),
        postgresql_where=sa.text(
            "task_type = 'face_scan_project' AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_project_tasks_one_active_face_scan", table_name="project_tasks")
