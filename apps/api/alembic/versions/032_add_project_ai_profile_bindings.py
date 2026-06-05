"""add project ai profile bindings

Revision ID: 032_project_ai_profile_bindings
Revises: 031_users_permissions_ai_profiles
Create Date: 2026-06-05
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032_project_ai_profile_bindings"
down_revision: Union[str, None] = "031_users_permissions_ai_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_ai_settings",
        sa.Column("ai_service_profile_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_project_ai_settings_ai_service_profile_id",
        "project_ai_settings",
        ["ai_service_profile_id"],
    )
    op.create_foreign_key(
        "fk_project_ai_settings_ai_service_profile_id",
        "project_ai_settings",
        "ai_service_profiles",
        ["ai_service_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "project_embedding_settings",
        sa.Column("ai_service_profile_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_project_embedding_settings_ai_service_profile_id",
        "project_embedding_settings",
        ["ai_service_profile_id"],
    )
    op.create_foreign_key(
        "fk_project_embedding_settings_ai_service_profile_id",
        "project_embedding_settings",
        "ai_service_profiles",
        ["ai_service_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "project_query_planner_settings",
        sa.Column("ai_service_profile_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_project_query_planner_settings_ai_service_profile_id",
        "project_query_planner_settings",
        ["ai_service_profile_id"],
    )
    op.create_foreign_key(
        "fk_project_query_planner_settings_ai_service_profile_id",
        "project_query_planner_settings",
        "ai_service_profiles",
        ["ai_service_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_query_planner_settings_ai_service_profile_id",
        "project_query_planner_settings",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_project_query_planner_settings_ai_service_profile_id",
        table_name="project_query_planner_settings",
    )
    op.drop_column("project_query_planner_settings", "ai_service_profile_id")

    op.drop_constraint(
        "fk_project_embedding_settings_ai_service_profile_id",
        "project_embedding_settings",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_project_embedding_settings_ai_service_profile_id",
        table_name="project_embedding_settings",
    )
    op.drop_column("project_embedding_settings", "ai_service_profile_id")

    op.drop_constraint(
        "fk_project_ai_settings_ai_service_profile_id",
        "project_ai_settings",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_project_ai_settings_ai_service_profile_id",
        table_name="project_ai_settings",
    )
    op.drop_column("project_ai_settings", "ai_service_profile_id")
