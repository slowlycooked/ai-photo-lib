"""Add project_embedding_settings and content_embedding fields

Revision ID: 015_semantic_search_upgrade
Revises: 014_fix_photo_embeddings
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "015_semantic_search_upgrade"
down_revision: Union[str, None] = "014_fix_photo_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    # ── 1. New table: project_embedding_settings ──────────────────────────────
    op.create_table(
        "project_embedding_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "provider",
            sa.Text(),
            server_default=sa.text("'openai-compatible'"),
            nullable=False,
        ),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "embedding_dimension",
            sa.Integer(),
            server_default=sa.text("1024"),
            nullable=False,
        ),
        sa.Column(
            "batch_size",
            sa.Integer(),
            server_default=sa.text("16"),
            nullable=False,
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            server_default=sa.text("60"),
            nullable=False,
        ),
        sa.Column("input_prefix_query", sa.Text(), nullable=True),
        sa.Column("input_prefix_document", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
            name="fk_project_embedding_settings_project_id",
        ),
        sa.UniqueConstraint("project_id", name="uq_project_embedding_settings_project_id"),
    )
    op.create_index(
        "ix_project_embedding_settings_project_id",
        "project_embedding_settings",
        ["project_id"],
    )

    # ── 2. Add content_embedding, content_text_hash, embedding_input_version
    #        to photo_embeddings ──────────────────────────────────────────────
    op.add_column(
        "photo_embeddings",
        sa.Column("content_embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    op.add_column(
        "photo_embeddings",
        sa.Column("content_text_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "photo_embeddings",
        sa.Column("embedding_input_version", sa.Text(), nullable=True),
    )

    # HNSW index on content_embedding for fast cosine search
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_photo_embeddings_content_hnsw
        ON photo_embeddings
        USING hnsw (content_embedding vector_cosine_ops)
        WHERE content_embedding IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_photo_embeddings_content_hnsw")
    op.drop_column("photo_embeddings", "embedding_input_version")
    op.drop_column("photo_embeddings", "content_text_hash")
    op.drop_column("photo_embeddings", "content_embedding")
    op.drop_index(
        "ix_project_embedding_settings_project_id",
        table_name="project_embedding_settings",
    )
    op.drop_table("project_embedding_settings")
