"""add active photo quarantine task uniqueness

Revision ID: 037_add_photo_quarantine_task_index
Revises: 036_add_photo_quarantine
Create Date: 2026-08-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "037_add_photo_quarantine_task_index"
down_revision: Union[str, None] = "036_add_photo_quarantine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_project_tasks_one_active_photo_quarantine",
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(
            "task_type = 'photo_quarantine_analysis' AND status IN ('queued', 'running')"
        ),
        postgresql_where=sa.text(
            "task_type = 'photo_quarantine_analysis' AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_project_tasks_one_active_photo_quarantine",
        table_name="project_tasks",
    )
