"""allow three concurrent face rematch tasks per project

Revision ID: 040_face_rematch_concurrency_3
Revises: 039_query_planner_v2_defaults
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "040_face_rematch_concurrency_3"
down_revision: Union[str, None] = "039_query_planner_v2_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "uq_project_tasks_one_active_face_rematch"
_ACTIVE_PREDICATE = (
    "task_type = 'face_rematch_unknown' AND status IN ('queued', 'running')"
)


def upgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="project_tasks")


def downgrade() -> None:
    bind = op.get_bind()
    active_tasks = bind.execute(
        sa.text(
            """
            SELECT id, project_id
            FROM project_tasks
            WHERE task_type = 'face_rematch_unknown'
              AND status IN ('queued', 'running')
            ORDER BY project_id, created_at, id
            """
        )
    ).fetchall()

    seen_projects: set[int] = set()
    for task_id, project_id in active_tasks:
        normalized_project_id = int(project_id)
        if normalized_project_id not in seen_projects:
            seen_projects.add(normalized_project_id)
            continue
        bind.execute(
            sa.text(
                "UPDATE project_tasks SET status = 'pending' WHERE id = :task_id"
            ),
            {"task_id": task_id},
        )

    op.create_index(
        _INDEX_NAME,
        "project_tasks",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE_PREDICATE),
        postgresql_where=sa.text(_ACTIVE_PREDICATE),
    )
