"""add vector search weights to project_embedding_settings

Revision ID: 016_add_vector_search_weights
Revises: 015_semantic_search_upgrade
Create Date: 2026-05-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_vector_search_weights"
down_revision: Union[str, None] = "015_semantic_search_upgrade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_embedding_settings",
        sa.Column(
            "search_content_vector_weight",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
    )
    op.add_column(
        "project_embedding_settings",
        sa.Column(
            "search_tag_vector_weight",
            sa.Float(),
            nullable=False,
            server_default="0.25",
        ),
    )
    op.add_column(
        "project_embedding_settings",
        sa.Column(
            "search_caption_vector_weight",
            sa.Float(),
            nullable=False,
            server_default="0.2",
        ),
    )
    op.add_column(
        "project_embedding_settings",
        sa.Column(
            "search_ocr_vector_weight",
            sa.Float(),
            nullable=False,
            server_default="0.05",
        ),
    )


def downgrade() -> None:
    op.drop_column("project_embedding_settings", "search_ocr_vector_weight")
    op.drop_column("project_embedding_settings", "search_caption_vector_weight")
    op.drop_column("project_embedding_settings", "search_tag_vector_weight")
    op.drop_column("project_embedding_settings", "search_content_vector_weight")
