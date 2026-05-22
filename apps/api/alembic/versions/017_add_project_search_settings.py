"""Add project_search_settings table.

Revision ID: 017_add_project_search_settings
Revises: 016_add_vector_search_weights
Create Date: 2024-01-01
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "017_add_project_search_settings"
down_revision: Union[str, None] = "016_add_vector_search_weights"
branch_labels = None
depends_on = None

_DEFAULT_KEYWORD_FIELD_WEIGHTS = (
    '{"caption": 3, "ocr_text": 5, "scene_tags": 4, "object_tags": 4, '
    '"activity_tags": 4, "search_keywords": 4, "quality_tags": 2, '
    '"location_clues": 2, "file_name": 1}'
)
_DEFAULT_VECTOR_FIELD_WEIGHTS = (
    '{"content_embedding": 0.5, "tag_embedding": 0.25, '
    '"caption_embedding": 0.2, "ocr_embedding": 0.05}'
)
_DEFAULT_OCR_VECTOR_FIELD_WEIGHTS = (
    '{"content_embedding": 0.35, "tag_embedding": 0.15, '
    '"caption_embedding": 0.1, "ocr_embedding": 0.4}'
)


def upgrade() -> None:
    op.create_table(
        "project_search_settings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Search mode & recall sizing
        sa.Column("default_mode", sa.Text, server_default="hybrid", nullable=False),
        sa.Column("keyword_top_k", sa.Integer, server_default="2000", nullable=False),
        sa.Column("vector_top_k", sa.Integer, server_default="200", nullable=False),
        sa.Column("page_size_default", sa.Integer, server_default="50", nullable=False),
        sa.Column("page_size_max", sa.Integer, server_default="200", nullable=False),
        # Fusion parameters
        sa.Column("rrf_k", sa.Integer, server_default="60", nullable=False),
        sa.Column("keyword_weight", sa.Float, server_default="0.55", nullable=False),
        sa.Column("vector_weight", sa.Float, server_default="0.45", nullable=False),
        sa.Column("vector_min_score", sa.Float, server_default="0.25", nullable=False),
        # Field weights (JSONB)
        sa.Column(
            "keyword_field_weights",
            JSONB,
            server_default=_DEFAULT_KEYWORD_FIELD_WEIGHTS,
            nullable=True,
        ),
        sa.Column(
            "vector_field_weights",
            JSONB,
            server_default=_DEFAULT_VECTOR_FIELD_WEIGHTS,
            nullable=True,
        ),
        sa.Column(
            "ocr_query_vector_field_weights",
            JSONB,
            server_default=_DEFAULT_OCR_VECTOR_FIELD_WEIGHTS,
            nullable=True,
        ),
        # Feature flags
        sa.Column(
            "enable_query_understanding", sa.Boolean, server_default="true", nullable=False
        ),
        sa.Column(
            "enable_structured_filters", sa.Boolean, server_default="false", nullable=False
        ),
        sa.Column(
            "enable_semantic_tag_boost", sa.Boolean, server_default="false", nullable=False
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
    )

    op.create_index(
        "ix_project_search_settings_project_id",
        "project_search_settings",
        ["project_id"],
    )
    op.create_unique_constraint(
        "uq_project_search_settings_project_id",
        "project_search_settings",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_project_search_settings_project_id",
        "project_search_settings",
        type_="unique",
    )
    op.drop_index(
        "ix_project_search_settings_project_id",
        table_name="project_search_settings",
    )
    op.drop_table("project_search_settings")
