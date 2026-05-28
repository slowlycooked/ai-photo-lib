"""set query planner enabled default true

Revision ID: 030_qp_enabled_default_true
Revises: 029_query_planner_settings
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030_qp_enabled_default_true"
down_revision: Union[str, None] = "029_query_planner_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "project_query_planner_settings",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("true"),
    )


def downgrade() -> None:
    op.alter_column(
        "project_query_planner_settings",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.text("false"),
    )
