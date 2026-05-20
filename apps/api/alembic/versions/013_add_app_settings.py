"""Add app_settings table for global debug config

Revision ID: 013_add_app_settings
Revises: 012_fix_photo_embeddings_schema
Create Date: 2026-05-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_add_app_settings"
down_revision: Union[str, None] = "012_fix_photo_embeddings_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), primary_key=True, nullable=False),
        sa.Column('value_json', postgresql.JSONB, nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
