from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..models.photo import Photo

TASK_IMAGE_ANALYSIS = "image_analysis"

_DEFAULT_USER_PROMPT = """请重点分析以下内容：
- 场景
- 人物
- 建筑
- 地点线索
- OCR 文字
- 照片质量
- 搜索关键词

如果无法判断，请给出低置信度并保持字段完整。"""

_FIXED_SYSTEM_PREFIX = """你是一个图片分析 JSON API。
你必须严格遵守以下规则：
1. 只输出一个 JSON 对象。
2. 输出的第一个字符必须是 {。
3. 输出的最后一个字符必须是 }。
4. 不要输出 Markdown。
5. 不要输出解释。
6. 不要输出推理过程。
7. 如果无法判断，使用空数组、空字符串、0 或较低 confidence。
8. people_count 必须是数字。
9. confidence 必须是 0 到 1 之间的数字。"""

_FIXED_SCHEMA_SUFFIX = """
JSON 字段必须严格为：
{
  "caption": "string",
  "scene_tags": ["string"],
  "object_tags": ["string"],
  "activity_tags": ["string"],
  "people_count": 0,
  "ocr_text": ["string"],
  "location_clues": ["string"],
  "quality_tags": ["string"],
  "search_keywords": ["string"],
  "confidence": 0.0
}

现在分析图片。只返回 JSON。"""

_VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def default_output_schema() -> dict[str, Any]:
    return {
        "caption": "string",
        "scene_tags": ["string"],
        "object_tags": ["string"],
        "activity_tags": ["string"],
        "people_count": 0,
        "ocr_text": ["string"],
        "location_clues": ["string"],
        "quality_tags": ["string"],
        "search_keywords": ["string"],
        "confidence": 0.0,
    }


def build_default_template(project_id: int) -> ProjectPromptTemplate:
    return ProjectPromptTemplate(
        project_id=project_id,
        name="默认图片分析模板",
        task_type=TASK_IMAGE_ANALYSIS,
        system_prompt=None,
        user_prompt=_DEFAULT_USER_PROMPT,
        output_schema=default_output_schema(),
        is_active=True,
        version=1,
    )


def _default_endpoint_url() -> str:
    return f"{settings.openai_base_url.rstrip('/')}/chat/completions"


def _maybe_upgrade_legacy_endpoint(settings_row: ProjectAISettings) -> None:
    legacy_endpoints = {
        "http://127.0.0.1:8082/v1/chat/completions",
        "http://localhost:8082/v1/chat/completions",
    }
    default_endpoint = _default_endpoint_url()
    current_endpoint = (settings_row.endpoint_url or "").strip()

    # Keep explicit custom endpoints untouched, but auto-heal known local legacy
    # defaults so existing projects continue to work after port changes.
    if not current_endpoint or (
        current_endpoint in legacy_endpoints and default_endpoint not in legacy_endpoints
    ):
        settings_row.endpoint_url = default_endpoint
        settings_row.updated_at = datetime.now(timezone.utc)


def get_or_create_project_ai_settings(db: Session, project_id: int) -> ProjectAISettings:
    settings_row = (
        db.query(ProjectAISettings)
        .filter(ProjectAISettings.project_id == project_id)
        .first()
    )
    if settings_row:
        _maybe_upgrade_legacy_endpoint(settings_row)
        return settings_row

    template = build_default_template(project_id)
    db.add(template)
    db.flush()

    settings_row = ProjectAISettings(
        project_id=project_id,
        provider="llama-server",
        endpoint_url=_default_endpoint_url(),
        model_name=settings.openai_vision_model,
        temperature=settings.ai_vision_temperature,
        top_p=0.8,
        max_tokens=max(settings.ai_vision_max_tokens, 256),
        retry_count=1,
        output_language="zh-CN",
        json_parse_strategy="auto_extract",
        active_prompt_template_id=template.id,
    )
    db.add(settings_row)
    db.flush()
    return settings_row


def get_active_prompt_template(
    db: Session,
    project_id: int,
    *,
    task_type: str = TASK_IMAGE_ANALYSIS,
    template_id: int | None = None,
) -> ProjectPromptTemplate:
    if template_id is not None:
        template = (
            db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.id == template_id,
                ProjectPromptTemplate.task_type == task_type,
            )
            .first()
        )
        if template:
            return template

    template = (
        db.query(ProjectPromptTemplate)
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == task_type,
            ProjectPromptTemplate.is_active.is_(True),
        )
        .order_by(ProjectPromptTemplate.version.desc(), ProjectPromptTemplate.id.desc())
        .first()
    )
    if template:
        return template

    template = build_default_template(project_id)
    db.add(template)
    db.flush()
    return template


def activate_prompt_template(
    db: Session,
    project_id: int,
    template: ProjectPromptTemplate,
    *,
    task_type: str = TASK_IMAGE_ANALYSIS,
) -> None:
    db.query(ProjectPromptTemplate).filter(
        ProjectPromptTemplate.project_id == project_id,
        ProjectPromptTemplate.task_type == task_type,
    ).update({"is_active": False})
    template.is_active = True
    template.updated_at = datetime.now(timezone.utc)

    settings_row = get_or_create_project_ai_settings(db, project_id)
    settings_row.active_prompt_template_id = template.id
    settings_row.updated_at = datetime.now(timezone.utc)


def _build_prompt_variables(photo: Photo) -> dict[str, str]:
    exif_json = photo.exif if isinstance(photo.exif, dict) else {}
    return {
        "filename": photo.file_name or "",
        "folder_path": photo.folder_path or "",
        "taken_at": photo.taken_at.isoformat() if photo.taken_at else "",
        "exif_json": str(exif_json),
        "gps_text": (
            f"lat={photo.gps_latitude},lng={photo.gps_longitude},alt={photo.gps_altitude}"
            if photo.gps_latitude is not None and photo.gps_longitude is not None
            else ""
        ),
    }


def _render_template_variables(template_text: str, values: dict[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    return _VARIABLE_PATTERN.sub(_replace, template_text)


def render_analysis_prompt(
    *,
    photo: Photo,
    prompt_template: ProjectPromptTemplate,
    output_language: str,
    override_prompt: str | None = None,
) -> str:
    user_prompt = override_prompt if override_prompt else prompt_template.user_prompt
    variables = _build_prompt_variables(photo)
    rendered_user_prompt = _render_template_variables(user_prompt, variables)

    language_line = f"所有文本字段必须使用{output_language}。"

    system_prompt = prompt_template.system_prompt.strip() if prompt_template.system_prompt else ""
    parts = [_FIXED_SYSTEM_PREFIX, language_line]
    if system_prompt:
        parts.append(system_prompt)
    parts.extend([rendered_user_prompt, _FIXED_SCHEMA_SUFFIX])
    return "\n\n".join(p for p in parts if p.strip())
