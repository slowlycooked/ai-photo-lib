"""expand alembic_version.version_num length

Revision ID: 021a_expand_alembic_version_len
Revises: 021_add_photo_derivatives
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021a_expand_alembic_version_len"
down_revision: Union[str, None] = "021_add_photo_derivatives"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=255),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            existing_type=sa.String(length=255),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
