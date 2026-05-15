"""create photos table

Revision ID: 001
Revises:
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("file_path", sa.Text, unique=True, nullable=False),
        sa.Column("file_name", sa.Text, nullable=False),
        sa.Column("file_hash", sa.Text, nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.Text, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("taken_at", sa.TIMESTAMP, nullable=True),
        sa.Column("exif", sa.JSON, nullable=True),
        sa.Column("thumbnail_path", sa.Text, nullable=True),
        sa.Column("status", sa.Text, server_default="pending", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP, nullable=True),
    )
    op.create_index("ix_photos_status", "photos", ["status"])
    op.create_index("ix_photos_taken_at", "photos", ["taken_at"])
    op.create_index("ix_photos_file_hash", "photos", ["file_hash"])


def downgrade() -> None:
    op.drop_table("photos")
