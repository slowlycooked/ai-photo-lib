"""set query planner v2 defaults

Revision ID: 039_query_planner_v2_defaults
Revises: 038_photo_library_browse_indexes
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "039_query_planner_v2_defaults"
down_revision: Union[str, None] = "038_photo_library_browse_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "project_query_planner_settings",
        "max_tokens",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="512",
    )
    op.alter_column(
        "project_query_planner_settings",
        "planner_version",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="llm_query_planner_v2",
    )

    # Upgrade only rows that still match the shipped V1 defaults. Explicit V1
    # selections or custom prompts remain untouched as a project-level feature flag.
    op.execute(
        sa.text(
            """
            UPDATE project_query_planner_settings
            SET planner_version = 'llm_query_planner_v2',
                top_p = 0.8,
                max_tokens = 512
            WHERE planner_version = 'llm_query_planner_v1'
              AND COALESCE(prompt_template, '') = ''
              AND COALESCE(system_prompt, '') = ''
              AND fallback_mode = 'rule_fallback'
              AND temperature BETWEEN 0 AND 0.1
              AND top_p IN (0.1, 0.8)
              AND max_tokens IN (220, 700)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE project_query_planner_settings
            SET planner_version = 'llm_query_planner_v1',
                max_tokens = 700
            WHERE planner_version = 'llm_query_planner_v2'
              AND COALESCE(prompt_template, '') = ''
              AND COALESCE(system_prompt, '') = ''
              AND fallback_mode = 'rule_fallback'
              AND temperature BETWEEN 0 AND 0.1
              AND top_p = 0.8
              AND max_tokens = 512
            """
        )
    )
    op.alter_column(
        "project_query_planner_settings",
        "planner_version",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="llm_query_planner_v1",
    )
    op.alter_column(
        "project_query_planner_settings",
        "max_tokens",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="700",
    )
