"""Add search_quality_settings JSONB column to project_search_settings.

Revision ID: 018_add_search_quality_settings
Revises: 017_add_project_search_settings
Create Date: 2024-01-01
"""
from __future__ import annotations

from typing import Union

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "018_add_search_quality_settings"
down_revision: Union[str, None] = "017_add_project_search_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_search_settings",
        # Nullable JSONB column — NULL means "use EffectiveSearchSettings defaults"
        # Supported keys (all optional):
        #   vector_strict_score: float        default 0.42
        #   min_display_evidence_level: str   default "C"  (A/B/C/D/E/F)
        #   enable_evidence_filter: bool      default true
        #   enable_negative_penalty: bool     default true
        #   evidence_weight: float            default 0.02
        #   negative_term_penalty: float      default 0.01
        __import__("sqlalchemy").Column("search_quality_settings", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_search_settings", "search_quality_settings")
