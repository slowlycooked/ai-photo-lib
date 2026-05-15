"""add ai analysis and jobs tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # photo_ai_analysis
    op.create_table(
        "photo_ai_analysis",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "photo_id",
            sa.BigInteger,
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.Text, nullable=True),
        sa.Column("model_version", sa.Text, nullable=True),
        sa.Column("caption", sa.Text, nullable=True),
        sa.Column("ocr_text", sa.Text, nullable=True),
        sa.Column("scene_tags", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("object_tags", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("activity_tags", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("quality_tags", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("location_clues", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("search_keywords", sa.ARRAY(sa.Text), nullable=True),
        sa.Column("people_count", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("raw_result", sa.JSON, nullable=True),
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
    op.create_index("ix_photo_ai_analysis_photo_id", "photo_ai_analysis", ["photo_id"])

    # ai_jobs
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "photo_id",
            sa.BigInteger,
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.Text, nullable=True),
        sa.Column("status", sa.Text, server_default="queued", nullable=False),
        sa.Column("retry_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.TIMESTAMP, nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP, nullable=True),
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
    op.create_index("ix_ai_jobs_photo_id", "ai_jobs", ["photo_id"])
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("ai_jobs")
    op.drop_table("photo_ai_analysis")
