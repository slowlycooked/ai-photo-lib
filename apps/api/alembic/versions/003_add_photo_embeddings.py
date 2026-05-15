"""add photo_embeddings table (placeholder for v0.4 pgvector)

Revision ID: 003
Revises: 002
Create Date: 2026-05-15

The embedding columns are stored as TEXT (JSON-serialised float arrays) so
this migration runs without the pgvector Python package.  They will be
migrated to the native `vector` type in v0.4 once pgvector is added.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_embeddings",
        sa.Column(
            "photo_id",
            sa.BigInteger,
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Placeholder columns — will become vector(1024) in v0.4
        sa.Column("caption_embedding", sa.Text, nullable=True),
        sa.Column("tag_embedding", sa.Text, nullable=True),
        sa.Column("ocr_embedding", sa.Text, nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("photo_embeddings")
