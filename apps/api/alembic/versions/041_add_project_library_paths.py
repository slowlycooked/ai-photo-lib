"""add project_library_paths (1 project : N library paths)

Revision ID: 041_add_project_library_paths
Revises: 040_face_rematch_concurrency_3
Create Date: 2026-10-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "041_add_project_library_paths"
down_revision: Union[str, None] = "040_face_rematch_concurrency_3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_library_paths",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "path", name="uq_project_library_paths_project_path"
        ),
    )
    op.create_index(
        "ix_project_library_paths_project_id",
        "project_library_paths",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_library_paths_project_position",
        "project_library_paths",
        ["project_id", "position"],
        unique=False,
    )

    # Backfill: seed every existing project with its single library path as the
    # primary (position 0) row. The table is fresh, so no conflict is possible.
    op.execute(
        """
        INSERT INTO project_library_paths (project_id, path, position, created_at, updated_at)
        SELECT id, photo_library_path, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM projects
        WHERE photo_library_path IS NOT NULL AND TRIM(photo_library_path) != ''
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_library_paths_project_position", table_name="project_library_paths"
    )
    op.drop_index("ix_project_library_paths_project_id", table_name="project_library_paths")
    op.drop_table("project_library_paths")
