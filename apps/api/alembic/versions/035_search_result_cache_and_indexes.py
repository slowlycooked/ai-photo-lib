"""add search result cache ttl setting and search performance indexes

Revision ID: 035_search_result_cache_and_indexes
Revises: 034_add_task_leases
Create Date: 2026-06-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "035_search_result_cache_and_indexes"
down_revision: Union[str, None] = "034_add_task_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_search_settings",
        sa.Column(
            "search_result_cache_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default="600",
        ),
    )

    op.create_index(
        "ix_photo_embeddings_project_status_model_dim_version",
        "photo_embeddings",
        [
            "project_id",
            "embedding_status",
            "embedding_model",
            "embedding_dimension",
            "embedding_input_version",
        ],
        unique=False,
    )
    op.create_index(
        "ix_photos_project_status_deleted_at",
        "photos",
        ["project_id", "status", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_photos_project_status_deleted_at", table_name="photos")
    op.drop_index(
        "ix_photo_embeddings_project_status_model_dim_version",
        table_name="photo_embeddings",
    )
    op.drop_column("project_search_settings", "search_result_cache_ttl_seconds")
