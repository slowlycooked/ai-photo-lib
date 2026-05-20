"""add embedding status/hash metadata columns

Revision ID: 012_embedding_status_meta
Revises: 011_pgvector_embeddings
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_embedding_status_meta"
down_revision: Union[str, None] = "011_pgvector_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("photo_embeddings", sa.Column("caption_text_hash", sa.Text(), nullable=True))
    op.add_column("photo_embeddings", sa.Column("tag_text_hash", sa.Text(), nullable=True))
    op.add_column("photo_embeddings", sa.Column("ocr_text_hash", sa.Text(), nullable=True))
    op.add_column("photo_embeddings", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    op.add_column(
        "photo_embeddings",
        sa.Column("embedding_status", sa.Text(), server_default=sa.text("'ready'"), nullable=False),
    )
    op.add_column("photo_embeddings", sa.Column("embedding_error", sa.Text(), nullable=True))
    op.add_column("photo_embeddings", sa.Column("embedded_at", sa.TIMESTAMP(), nullable=True))

    op.create_index(
        "ix_photo_embeddings_project_status",
        "photo_embeddings",
        ["project_id", "embedding_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_photo_embeddings_project_status", table_name="photo_embeddings")
    op.drop_column("photo_embeddings", "embedded_at")
    op.drop_column("photo_embeddings", "embedding_error")
    op.drop_column("photo_embeddings", "embedding_status")
    op.drop_column("photo_embeddings", "embedding_dimension")
    op.drop_column("photo_embeddings", "ocr_text_hash")
    op.drop_column("photo_embeddings", "tag_text_hash")
    op.drop_column("photo_embeddings", "caption_text_hash")
