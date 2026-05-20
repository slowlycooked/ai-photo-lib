"""enforce active prompt template belongs to same project

Revision ID: 010_active_prompt_same_project_fk
Revises: 009_project_isolation
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_active_prompt_same_project_fk"
down_revision: Union[str, None] = "009_project_isolation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Validate existing rows before adding the stricter FK.
    mismatch_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM project_ai_settings s
            LEFT JOIN project_prompt_templates t
              ON t.id = s.active_prompt_template_id
            WHERE s.active_prompt_template_id IS NOT NULL
              AND (t.id IS NULL OR t.project_id <> s.project_id)
            """
        )
    ).scalar_one()
    if mismatch_count:
        raise RuntimeError(
            "Cannot enforce same-project active prompt FK: "
            f"{mismatch_count} invalid rows found in project_ai_settings"
        )

    # Composite FK requires referenced columns to be uniquely addressable.
    op.create_unique_constraint(
        "uq_project_prompt_templates_project_id_id",
        "project_prompt_templates",
        ["project_id", "id"],
    )

    # Drop old single-column FK and replace with same-project composite FK.
    op.execute(
        "ALTER TABLE project_ai_settings "
        "DROP CONSTRAINT IF EXISTS project_ai_settings_active_prompt_template_id_fkey"
    )
    op.create_foreign_key(
        "fk_project_ai_settings_active_prompt_same_project",
        "project_ai_settings",
        "project_prompt_templates",
        ["project_id", "active_prompt_template_id"],
        ["project_id", "id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_project_ai_settings_active_prompt_same_project",
        "project_ai_settings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "project_ai_settings_active_prompt_template_id_fkey",
        "project_ai_settings",
        "project_prompt_templates",
        ["active_prompt_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "uq_project_prompt_templates_project_id_id",
        "project_prompt_templates",
        type_="unique",
    )
