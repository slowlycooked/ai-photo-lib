"""add photo_derivatives table

Revision ID: 021_add_photo_derivatives
Revises: 020_add_people_recognition_foundation
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_add_photo_derivatives"
down_revision: Union[str, None] = "020_add_people_recognition_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_derivatives",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        # ai_thumbnail | face_work_image | face_crop
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("format", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_mtime", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("source_hash", sa.Text(), nullable=True),
        sa.Column("quality", sa.Integer(), nullable=True),
        # ready | failed | missing_source
        sa.Column("status", sa.Text(), server_default="ready", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        # For face_crop rows: reference to the detection that produced this crop
        sa.Column("face_detection_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["photos.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["face_detection_id"],
            ["face_detections.id"],
            ondelete="SET NULL",
        ),
    )

    # Partial unique index: one ai_thumbnail / face_work_image per (project, photo).
    # face_crop rows are excluded — there can be multiple per photo (one per face).
    op.execute(
        """
        CREATE UNIQUE INDEX ix_photo_derivatives_unique_non_crop
        ON photo_derivatives (project_id, photo_id, kind)
        WHERE kind != 'face_crop'
        """
    )

    op.create_index(
        "ix_photo_derivatives_project_photo",
        "photo_derivatives",
        ["project_id", "photo_id"],
    )
    op.create_index(
        "ix_photo_derivatives_project_kind",
        "photo_derivatives",
        ["project_id", "kind"],
    )
    op.create_index(
        "ix_photo_derivatives_face_detection",
        "photo_derivatives",
        ["face_detection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_photo_derivatives_face_detection", table_name="photo_derivatives")
    op.drop_index("ix_photo_derivatives_project_kind", table_name="photo_derivatives")
    op.drop_index("ix_photo_derivatives_project_photo", table_name="photo_derivatives")
    op.execute("DROP INDEX IF EXISTS ix_photo_derivatives_unique_non_crop")
    op.drop_table("photo_derivatives")
