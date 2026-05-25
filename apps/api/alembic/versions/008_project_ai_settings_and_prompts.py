"""add project-level ai settings and prompt templates

Revision ID: 008_proj_ai_settings
Revises: 007_add_project_folders
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_proj_ai_settings"
down_revision: Union[str, None] = "007_add_project_folders"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_prompt_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("task_type", sa.Text(), nullable=False, server_default="image_analysis"),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_project_prompt_templates_project_task",
        "project_prompt_templates",
        ["project_id", "task_type"],
        unique=False,
    )

    op.create_table(
        "project_ai_settings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False, server_default="llama-server"),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0"),
        sa.Column("top_p", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("output_language", sa.Text(), nullable=False, server_default="zh-CN"),
        sa.Column("json_parse_strategy", sa.Text(), nullable=False, server_default="auto_extract"),
        sa.Column(
            "active_prompt_template_id",
            sa.BigInteger(),
            sa.ForeignKey("project_prompt_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("project_id", name="uq_project_ai_settings_project_id"),
    )

    op.add_column(
        "ai_jobs",
        sa.Column(
            "prompt_template_id",
            sa.BigInteger(),
            sa.ForeignKey("project_prompt_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("ai_jobs", sa.Column("prompt_version", sa.Integer(), nullable=True))
    op.add_column("ai_jobs", sa.Column("model_name", sa.Text(), nullable=True))
    op.add_column("ai_jobs", sa.Column("model_params", sa.JSON(), nullable=True))
    op.add_column("ai_jobs", sa.Column("raw_model_output", sa.Text(), nullable=True))
    op.add_column("ai_jobs", sa.Column("parse_error", sa.Text(), nullable=True))

    op.create_index(
        "ix_ai_jobs_prompt_template_id",
        "ai_jobs",
        ["prompt_template_id"],
        unique=False,
    )

    # Seed one default prompt template + settings row for every existing project.
    op.execute(
        sa.text(
            """
            INSERT INTO project_prompt_templates (
                project_id, name, task_type, user_prompt, output_schema, is_active, version
            )
            SELECT
                p.id,
                '默认图片分析模板',
                'image_analysis',
                :user_prompt,
                CAST(:output_schema AS JSON),
                true,
                1
            FROM projects p
            WHERE p.deleted_at IS NULL;
            """
        ).bindparams(
            user_prompt=(
                "请重点分析场景、人物、建筑、地点线索、OCR文字、照片质量和搜索关键词。"
                "caption 使用自然中文完整描述。"
                "scene_tags、object_tags、activity_tags、quality_tags、location_clues、search_keywords "
                "必须优先使用简体中文标签。"
                "不要输出英文标签，不要输出拼音，不要输出中英混合重复标签。"
                "如果无法判断，给出低置信度并保持字段完整。"
            ),
            output_schema=(
                '{"caption":"string","scene_tags":["string"],"object_tags":["string"],'
                '"activity_tags":["string"],"people_count":0,"ocr_text":["string"],'
                '"location_clues":["string"],"quality_tags":["string"],'
                '"search_keywords":["string"],"confidence":0.0}'
            ),
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO project_ai_settings (
                project_id,
                provider,
                endpoint_url,
                model_name,
                temperature,
                top_p,
                max_tokens,
                retry_count,
                output_language,
                json_parse_strategy,
                active_prompt_template_id
            )
            SELECT
                p.id,
                'llama-server',
                :endpoint_url,
                :model_name,
                0,
                0.8,
                1024,
                1,
                'zh-CN',
                'auto_extract',
                t.id
            FROM projects p
            JOIN project_prompt_templates t
              ON t.project_id = p.id
             AND t.task_type = 'image_analysis'
             AND t.is_active = true
            WHERE p.deleted_at IS NULL
            ON CONFLICT (project_id) DO NOTHING;
            """
        ).bindparams(
            endpoint_url="http://127.0.0.1:8082/v1/chat/completions",
            model_name="MiniCPM-V-4.6",
        )
    )


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_prompt_template_id", table_name="ai_jobs")
    op.drop_column("ai_jobs", "parse_error")
    op.drop_column("ai_jobs", "raw_model_output")
    op.drop_column("ai_jobs", "model_params")
    op.drop_column("ai_jobs", "model_name")
    op.drop_column("ai_jobs", "prompt_version")
    op.drop_column("ai_jobs", "prompt_template_id")

    op.drop_table("project_ai_settings")
    op.drop_index("ix_project_prompt_templates_project_task", table_name="project_prompt_templates")
    op.drop_table("project_prompt_templates")
