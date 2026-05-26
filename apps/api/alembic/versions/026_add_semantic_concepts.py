"""add semantic_concepts to photo_ai_analysis

Revision ID: 026_add_semantic_concepts
Revises: 025_project_task_active_uniqueness
Create Date: 2026-05-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "026_add_semantic_concepts"
down_revision: Union[str, None] = "025_project_task_active_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "photo_ai_analysis",
        sa.Column("semantic_concepts", ARRAY(sa.Text()), nullable=True),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_photo_ai_analysis_semantic_concepts_gin "
            "ON photo_ai_analysis USING GIN (semantic_concepts)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_photo_ai_analysis_semantic_concepts_gin")

    op.drop_column("photo_ai_analysis", "semantic_concepts")
