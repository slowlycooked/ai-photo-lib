"""add project query planner settings

Revision ID: 029_query_planner_settings
Revises: 028_add_face_rematch_unknown_task_uniqueness
Create Date: 2026-05-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "029_query_planner_settings"
down_revision: Union[str, None] = "028_add_face_rematch_unknown_task_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_query_planner_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provider", sa.Text(), nullable=False, server_default="llama-server"),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0"),
        sa.Column("top_p", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="700"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column(
            "json_parse_strategy",
            sa.Text(),
            nullable=False,
            server_default="strict_json_then_extract",
        ),
        sa.Column(
            "planner_version",
            sa.Text(),
            nullable=False,
            server_default="llm_query_planner_v1",
        ),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("fallback_mode", sa.Text(), nullable=False, server_default="rule_fallback"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "project_id",
            name="uq_project_query_planner_settings_project_id",
        ),
    )
    op.create_index(
        "ix_project_query_planner_settings_project_id",
        "project_query_planner_settings",
        ["project_id"],
        unique=False,
    )

    # Backfill from legacy project_search_settings.search_quality_settings when present.
    op.execute(
        sa.text(
            """
            INSERT INTO project_query_planner_settings (
                project_id,
                enabled,
                provider,
                endpoint_url,
                api_key,
                model_name,
                temperature,
                top_p,
                max_tokens,
                timeout_seconds,
                json_parse_strategy,
                planner_version,
                prompt_template,
                system_prompt,
                fallback_mode
            )
            SELECT
                pss.project_id,
                COALESCE((pss.search_quality_settings ->> 'query_planner_enabled')::boolean, false),
                COALESCE(NULLIF(pss.search_quality_settings ->> 'query_planner_provider', ''), 'llama-server'),
                NULLIF(pss.search_quality_settings ->> 'query_planner_endpoint_url', ''),
                NULLIF(pss.search_quality_settings ->> 'query_planner_api_key', ''),
                NULLIF(pss.search_quality_settings ->> 'query_planner_model_name', ''),
                COALESCE((pss.search_quality_settings ->> 'query_planner_temperature')::double precision, 0),
                COALESCE((pss.search_quality_settings ->> 'query_planner_top_p')::double precision, 0.8),
                COALESCE((pss.search_quality_settings ->> 'query_planner_max_tokens')::integer, 700),
                COALESCE((pss.search_quality_settings ->> 'query_planner_timeout_seconds')::integer, 20),
                COALESCE(NULLIF(pss.search_quality_settings ->> 'query_planner_json_parse_strategy', ''), 'strict_json_then_extract'),
                COALESCE(NULLIF(pss.search_quality_settings ->> 'query_planner_planner_version', ''), 'llm_query_planner_v1'),
                NULLIF(pss.search_quality_settings ->> 'query_planner_prompt_template', ''),
                NULLIF(pss.search_quality_settings ->> 'query_planner_system_prompt', ''),
                COALESCE(NULLIF(pss.search_quality_settings ->> 'query_planner_fallback_mode', ''), 'rule_fallback')
            FROM project_search_settings pss
            WHERE pss.search_quality_settings IS NOT NULL
              AND (
                pss.search_quality_settings ? 'query_planner_enabled'
                OR pss.search_quality_settings ? 'query_planner_endpoint_url'
                OR pss.search_quality_settings ? 'query_planner_model_name'
              )
            ON CONFLICT (project_id) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_query_planner_settings_project_id",
        table_name="project_query_planner_settings",
    )
    op.drop_table("project_query_planner_settings")
