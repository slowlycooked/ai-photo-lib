"""add projects table and project_id to photos

Revision ID: 004
Revises: 003
Create Date: 2026-05-18
"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create projects table
    # ------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("photo_library_path", sa.Text, nullable=False),
        sa.Column("thumbnail_path", sa.Text, nullable=True),
        sa.Column(
            "is_default",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP,
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.TIMESTAMP, nullable=True),
    )

    # ------------------------------------------------------------------
    # 2. Insert default project using current env vars
    # ------------------------------------------------------------------
    photo_library_path = os.environ.get("PHOTO_LIBRARY_PATH")
    thumbnail_path = os.environ.get("THUMBNAIL_PATH")
    if not photo_library_path:
        raise RuntimeError("PHOTO_LIBRARY_PATH is required for projects migration")
    if not thumbnail_path:
        raise RuntimeError("THUMBNAIL_PATH is required for projects migration")

    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "INSERT INTO projects "
            "(name, description, photo_library_path, thumbnail_path, is_default) "
            "VALUES (:name, :desc, :path, :thumb, true) RETURNING id"
        ),
        {
            "name": "Default Library",
            "desc": "Default project (auto-created during migration)",
            "path": photo_library_path,
            "thumb": thumbnail_path,
        },
    )
    default_project_id = result.fetchone()[0]

    # ------------------------------------------------------------------
    # 3. Add project_id column to photos
    # ------------------------------------------------------------------
    op.add_column(
        "photos",
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # 4. Bind all existing photos to the default project
    # ------------------------------------------------------------------
    bind.execute(
        sa.text("UPDATE photos SET project_id = :pid WHERE project_id IS NULL"),
        {"pid": default_project_id},
    )

    # ------------------------------------------------------------------
    # 5. Create compound indexes for project-scoped queries
    # ------------------------------------------------------------------
    op.create_index(
        "ix_photos_project_taken_at", "photos", ["project_id", "taken_at"]
    )
    op.create_index(
        "ix_photos_project_status", "photos", ["project_id", "status"]
    )
    op.create_index(
        "ix_photos_project_file_hash", "photos", ["project_id", "file_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_photos_project_file_hash", table_name="photos")
    op.drop_index("ix_photos_project_status", table_name="photos")
    op.drop_index("ix_photos_project_taken_at", table_name="photos")
    op.drop_column("photos", "project_id")
    op.drop_table("projects")
