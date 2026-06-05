"""repair project task active indexes

Revision ID: 033_repair_project_task_active_indexes
Revises: 032_project_ai_profile_bindings
Create Date: 2026-06-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_repair_project_task_active_indexes"
down_revision: Union[str, None] = "032_project_ai_profile_bindings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    (
        "uq_project_tasks_one_active_scan",
        "task_type IN ('library_scan', 'library_reindex') AND status IN ('queued', 'running')",
    ),
    (
        "uq_project_tasks_one_active_face_cluster",
        "task_type = 'unknown_face_clustering' AND status IN ('queued', 'running')",
    ),
    (
        "uq_project_tasks_one_active_face_scan",
        "task_type = 'face_scan_project' AND status IN ('queued', 'running')",
    ),
    (
        "uq_project_tasks_one_active_face_rematch",
        "task_type = 'face_rematch_unknown' AND status IN ('queued', 'running')",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for index_name, predicate in _INDEXES:
            op.execute(
                sa.text(
                    f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS {index_name}
                    ON project_tasks (project_id)
                    WHERE {predicate}
                    """
                )
            )
        return

    existing = {index["name"] for index in sa.inspect(bind).get_indexes("project_tasks")}
    for index_name, predicate in _INDEXES:
        if index_name in existing:
            continue
        op.create_index(
            index_name,
            "project_tasks",
            ["project_id"],
            unique=True,
            sqlite_where=sa.text(predicate),
            postgresql_where=sa.text(predicate),
        )


def downgrade() -> None:
    for index_name, _predicate in reversed(_INDEXES):
        op.drop_index(index_name, table_name="project_tasks")
