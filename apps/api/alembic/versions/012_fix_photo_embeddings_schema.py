"""fix photo_embeddings schema to match ORM model

Revision ID: 012_fix_photo_embeddings_schema
Revises: 011_pgvector_embeddings
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "012_fix_photo_embeddings_schema"
down_revision: Union[str, None] = "011_pgvector_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("DROP TABLE IF EXISTS photo_embeddings CASCADE")

    op.create_table(
        "photo_embeddings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("photo_id", sa.BigInteger(), nullable=False),
        sa.Column("caption_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("tag_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("ocr_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("caption_text_hash", sa.Text(), nullable=True),
        sa.Column("tag_text_hash", sa.Text(), nullable=True),
        sa.Column("ocr_text_hash", sa.Text(), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column(
            "embedding_status",
            sa.Text(),
            server_default=sa.text("'ready'"),
            nullable=False,
        ),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        sa.Column("embedded_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "photo_id", name="uq_photo_embeddings_project_photo"),
    )

    op.create_index("ix_photo_embeddings_project_id", "photo_embeddings", ["project_id"])
    op.create_index("ix_photo_embeddings_photo_id", "photo_embeddings", ["photo_id"])
    op.create_index(
        "ix_photo_embeddings_project_status",
        "photo_embeddings",
        ["project_id", "embedding_status"],
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_photo_embeddings_caption_hnsw
        ON photo_embeddings
        USING hnsw (caption_embedding vector_cosine_ops)
        WHERE caption_embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_photo_embeddings_tag_hnsw
        ON photo_embeddings
        USING hnsw (tag_embedding vector_cosine_ops)
        WHERE tag_embedding IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_photo_embeddings_ocr_hnsw
        ON photo_embeddings
        USING hnsw (ocr_embedding vector_cosine_ops)
        WHERE ocr_embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photo_embeddings_ocr_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_photo_embeddings_tag_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_photo_embeddings_caption_hnsw")
    op.drop_index("ix_photo_embeddings_project_status", table_name="photo_embeddings")
    op.drop_index("ix_photo_embeddings_photo_id", table_name="photo_embeddings")
    op.drop_index("ix_photo_embeddings_project_id", table_name="photo_embeddings")
    op.drop_table("photo_embeddings")