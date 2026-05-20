"""Enforce project-isolation hard constraints

- photos.project_id NOT NULL (backfill from default project)
- drop global unique(file_path), add unique(project_id, file_path)
- add composite indexes on photos(project_id, taken_at/status/folder_id)
- ai_jobs.project_id NOT NULL (backfill from photos)
- photo_ai_analysis: add project_id NOT NULL, unique(project_id, photo_id),
  index(project_id, created_at)

Revision ID: 009_project_isolation
Revises: 008_proj_ai_settings
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_project_isolation"
down_revision: Union[str, None] = "008_proj_ai_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ──────────────────────────────────────────────────────────────────────────
    # 1. photos.project_id NOT NULL
    # ──────────────────────────────────────────────────────────────────────────

    # Backfill: any photo without a project_id gets assigned to the default
    # project (is_default = true).  If no default project exists yet we leave
    # the row NULL for now and the NOT NULL alter will fail loudly — which is
    # the correct explicit-failure behaviour.
    conn.execute(
        sa.text(
            """
            UPDATE photos
            SET project_id = (
                SELECT id FROM projects
                WHERE is_default = TRUE AND deleted_at IS NULL
                ORDER BY id
                LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
    )

    # Drop the old FK constraint that was created with nullable=True so we can
    # redefine it.  Alembic alter_column with existing_nullable keeps the FK;
    # we alter the column directly.
    op.alter_column(
        "photos",
        "project_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. photos.file_path: replace global unique with per-project unique
    # ──────────────────────────────────────────────────────────────────────────

    # PostgreSQL names an inline `unique=True` column constraint as
    # <table>_<column>_key.  Drop it and replace with a named constraint so
    # the downgrade can find it reliably.
    op.drop_constraint("photos_file_path_key", "photos", type_="unique")
    op.create_unique_constraint(
        "uq_photos_project_file_path",
        "photos",
        ["project_id", "file_path"],
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Drop the old single-column indexes superseded by project-composite ones
    # ──────────────────────────────────────────────────────────────────────────

    # ix_photos_project_taken_at / ix_photos_project_status /
    # ix_photos_project_folder_taken_at were already created by migrations
    # 004 and 006, so we only need to drop the legacy single-column indexes
    # that were created by migration 001.
    op.drop_index("ix_photos_taken_at", table_name="photos")
    op.drop_index("ix_photos_status", table_name="photos")

    # ──────────────────────────────────────────────────────────────────────────
    # 4. ai_jobs.project_id NOT NULL
    # ──────────────────────────────────────────────────────────────────────────

    # Backfill from the associated photo's project_id (already migrated above).
    conn.execute(
        sa.text(
            """
            UPDATE ai_jobs
            SET project_id = photos.project_id
            FROM photos
            WHERE ai_jobs.photo_id = photos.id
              AND ai_jobs.project_id IS NULL
            """
        )
    )

    # Any orphaned jobs (photo deleted) get the default project so the NOT NULL
    # alter succeeds.  These rows are effectively stale and should be pruned.
    conn.execute(
        sa.text(
            """
            UPDATE ai_jobs
            SET project_id = (
                SELECT id FROM projects
                WHERE is_default = TRUE AND deleted_at IS NULL
                ORDER BY id
                LIMIT 1
            )
            WHERE project_id IS NULL
            """
        )
    )

    op.alter_column(
        "ai_jobs",
        "project_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 5. photo_ai_analysis: add project_id, unique(project_id, photo_id)
    # ──────────────────────────────────────────────────────────────────────────

    op.add_column(
        "photo_ai_analysis",
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # Backfill from the photo's project_id (guaranteed NOT NULL after step 1).
    conn.execute(
        sa.text(
            """
            UPDATE photo_ai_analysis
            SET project_id = photos.project_id
            FROM photos
            WHERE photo_ai_analysis.photo_id = photos.id
            """
        )
    )

    op.alter_column(
        "photo_ai_analysis",
        "project_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_photo_ai_analysis_project_photo",
        "photo_ai_analysis",
        ["project_id", "photo_id"],
    )
    op.create_index(
        "ix_photo_ai_analysis_project_created_at",
        "photo_ai_analysis",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    # photo_ai_analysis
    op.drop_index("ix_photo_ai_analysis_project_created_at", table_name="photo_ai_analysis")
    op.drop_constraint("uq_photo_ai_analysis_project_photo", "photo_ai_analysis", type_="unique")
    op.alter_column("photo_ai_analysis", "project_id", existing_type=sa.BigInteger(), nullable=True)
    op.drop_column("photo_ai_analysis", "project_id")

    # ai_jobs
    op.alter_column("ai_jobs", "project_id", existing_type=sa.BigInteger(), nullable=True)

    # Restore the single-column indexes removed in upgrade step 3
    op.create_index("ix_photos_status", "photos", ["status"])
    op.create_index("ix_photos_taken_at", "photos", ["taken_at"])
    # Note: ix_photos_project_taken_at / _status / _folder_taken_at are
    # managed by migrations 004 and 006 — do NOT drop them here.

    # photos unique constraint
    op.drop_constraint("uq_photos_project_file_path", "photos", type_="unique")
    op.create_unique_constraint("photos_file_path_key", "photos", ["file_path"])

    # photos NOT NULL
    op.alter_column("photos", "project_id", existing_type=sa.BigInteger(), nullable=True)
