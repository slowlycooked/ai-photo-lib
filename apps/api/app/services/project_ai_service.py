from __future__ import annotations

import re
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..models.user import AIServiceProfile
from ..models.photo import Photo

TASK_IMAGE_ANALYSIS = "image_analysis"

logger = logging.getLogger(__name__)

_LEGACY_DEFAULT_USER_PROMPTS = {
    "请重点分析场景、人物、建筑、地点线索、OCR文字、照片质量和搜索关键词。如果无法判断，给出低置信度并保持字段完整。",
    "请重点分析以下内容：\n- 场景\n- 人物\n- 建筑\n- 地点线索\n- OCR 文字\n- 照片质量\n- 搜索关键词\n\n如果无法判断，请给出低置信度并保持字段完整。",
}

_DEFAULT_USER_PROMPT = """请重点分析以下内容：
- 场景
- 人物
- 建筑
- 地点线索
- OCR 文字
- 照片质量
- 搜索关键词

重要要求：
- caption 使用自然中文完整描述。
- scene_tags、object_tags、activity_tags、quality_tags、location_clues、search_keywords 必须优先使用简体中文标签。
- 不要输出英文标签，不要输出拼音，不要输出中英混合重复标签。
- 如果模型想到的是英文概念，请先翻译成最自然、最常见的中文再写入 JSON。

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

_STRICT_JSON_RETRY_PREFIX = """上一次输出无效，因为包含解释或推理过程。

现在重新输出。
只能输出 JSON。
第一个字符必须是 {。
最后一个字符必须是 }。
禁止输出“首先”“我需要”“根据规则”“让我”“现在”等文字。
不要解释。
不要 Markdown。"""

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


def _maybe_upgrade_legacy_template(template: ProjectPromptTemplate) -> None:
    if template.task_type != TASK_IMAGE_ANALYSIS:
        return
    if template.name and not template.name.startswith("默认图片分析模板"):
        return

    normalized_prompt = " ".join((template.user_prompt or "").split())
    normalized_legacy = {" ".join(p.split()) for p in _LEGACY_DEFAULT_USER_PROMPTS}
    normalized_current = " ".join(_DEFAULT_USER_PROMPT.split())
    if normalized_prompt in normalized_legacy and normalized_prompt != normalized_current:
        template.user_prompt = _DEFAULT_USER_PROMPT
        template.updated_at = datetime.now(timezone.utc)


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
        if not (settings_row.output_language or "").lower().startswith("zh"):
            settings_row.output_language = "zh-CN"
            settings_row.updated_at = datetime.now(timezone.utc)
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
        max_tokens=settings.ai_vision_max_tokens,
        retry_count=1,
        output_language="zh-CN",
        json_parse_strategy="auto_extract",
        active_prompt_template_id=template.id,
    )
    db.add(settings_row)
    db.flush()
    return settings_row


def get_project_ai_settings_strict(db: Session, project_id: int) -> ProjectAISettings:
    """Return project AI settings without creating defaults or auto-upgrading."""
    settings_row = (
        db.query(ProjectAISettings)
        .filter(ProjectAISettings.project_id == project_id)
        .first()
    )
    if settings_row is None:
        raise RuntimeError(
            f"AI settings are not configured for project_id={project_id}. "
            "Configure them via /projects/{id}/ai-settings before running analysis tasks."
        )
    if (
        settings_row.ai_service_profile_id is None
        and (
            not (settings_row.endpoint_url or "").strip()
            or not (settings_row.model_name or "").strip()
        )
    ):
        raise RuntimeError(
            f"AI settings for project_id={project_id} are incomplete. "
            "endpoint_url and model_name are required."
        )
    return settings_row


def resolve_project_ai_runtime_settings(db: Session, project_id: int) -> dict[str, Any]:
    row = get_project_ai_settings_strict(db, project_id)
    profile: AIServiceProfile | None = None
    if row.ai_service_profile_id is not None:
        profile = (
            db.query(AIServiceProfile)
            .filter(
                AIServiceProfile.id == row.ai_service_profile_id,
                AIServiceProfile.enabled.is_(True),
            )
            .first()
        )
        if profile is None:
            raise RuntimeError(
                f"AI service profile {row.ai_service_profile_id} is not available for project_id={project_id}."
            )
        if profile.capability != "vision":
            raise RuntimeError(
                f"AI service profile {profile.id} has capability={profile.capability!r}; expected 'vision'."
            )

    endpoint_url = (profile.endpoint_url if profile is not None else row.endpoint_url) or ""
    model_name = (profile.model_name if profile is not None else row.model_name) or ""
    provider = (profile.provider if profile is not None else row.provider) or ""
    if not endpoint_url.strip() or not model_name.strip():
        raise RuntimeError(
            f"AI runtime settings for project_id={project_id} are incomplete. "
            "endpoint_url and model_name are required."
        )
    return {
        "provider": provider,
        "endpoint_url": endpoint_url,
        "api_key": profile.api_key if profile is not None else settings.openai_api_key,
        "model_name": model_name,
        "temperature": row.temperature,
        "top_p": row.top_p,
        "max_tokens": row.max_tokens,
        "retry_count": row.retry_count,
        "output_language": row.output_language,
        "json_parse_strategy": row.json_parse_strategy,
        "active_prompt_template_id": row.active_prompt_template_id,
        "ai_service_profile_id": row.ai_service_profile_id,
    }


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


def migrate_legacy_project_ai_defaults(db: Session, project_id: int) -> dict[str, bool]:
    """Apply one-time legacy default upgrades for a project.

    This function is intentionally opt-in. Runtime request handling must not
    mutate project settings/templates implicitly.
    """
    changed = {
        "endpoint_upgraded": False,
        "template_upgraded": False,
    }

    settings_row = (
        db.query(ProjectAISettings)
        .filter(ProjectAISettings.project_id == project_id)
        .first()
    )
    if settings_row is not None:
        before = (settings_row.endpoint_url or "").strip()
        _maybe_upgrade_legacy_endpoint(settings_row)
        after = (settings_row.endpoint_url or "").strip()
        changed["endpoint_upgraded"] = before != after

    template = (
        db.query(ProjectPromptTemplate)
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
            ProjectPromptTemplate.is_active.is_(True),
        )
        .order_by(ProjectPromptTemplate.version.desc(), ProjectPromptTemplate.id.desc())
        .first()
    )
    if template is not None:
        before_prompt = template.user_prompt
        _maybe_upgrade_legacy_template(template)
        changed["template_upgraded"] = before_prompt != template.user_prompt

    return changed


def get_active_prompt_template_strict(
    db: Session,
    project_id: int,
    *,
    task_type: str = TASK_IMAGE_ANALYSIS,
    template_id: int | None = None,
) -> ProjectPromptTemplate:
    """Return existing active prompt template without creating defaults."""
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
        if template is not None:
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
    if template is None:
        raise RuntimeError(
            f"Prompt template is not configured for project_id={project_id}. "
            "Create and activate one via /projects/{id}/prompt-templates before running analysis tasks."
        )
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
    system_text, user_text = render_analysis_prompt_parts(
        photo=photo,
        prompt_template=prompt_template,
        output_language=output_language,
        override_prompt=override_prompt,
    )
    return "\n\n".join(p for p in [system_text, user_text] if p.strip())


def render_analysis_prompt_parts(
    *,
    photo: Photo,
    prompt_template: ProjectPromptTemplate,
    output_language: str,
    override_prompt: str | None = None,
) -> tuple[str, str]:
    user_prompt = override_prompt if override_prompt else prompt_template.user_prompt
    variables = _build_prompt_variables(photo)
    rendered_user_prompt = _render_template_variables(user_prompt, variables)

    language_line = (
        f"所有文本字段必须使用{output_language}。"
        "所有标签字段和搜索关键词字段必须使用简体中文 Unicode 文本。"
        "禁止输出英文标签；如果概念来自英文，必须先翻译成中文。"
    )
    custom_system = prompt_template.system_prompt.strip() if prompt_template.system_prompt else ""

    system_text = "\n\n".join(
        p
        for p in [_FIXED_SYSTEM_PREFIX, language_line, custom_system, _FIXED_SCHEMA_SUFFIX]
        if p.strip()
    )

    user_text = "\n\n".join(
        [
            "请分析这张图片，并直接返回 JSON。",
            "不要解释，不要描述你的思考过程。",
            "所有标签和搜索关键词都必须是简体中文。",
            rendered_user_prompt,
        ]
    )

    return system_text, user_text


def should_retry_strict_json_output(raw_text: str) -> bool:
    stripped = raw_text.lstrip()
    return not stripped.startswith("{") or "{" not in stripped


def build_strict_json_retry_user_text() -> str:
    return _STRICT_JSON_RETRY_PREFIX


def analyze_with_strict_json_retry(
    *,
    analyze_image_fn: Callable[..., str],
    image_path: str,
    system_text: str,
    user_text: str,
    endpoint_url: str | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> str:
    raw_text = analyze_image_fn(
        image_path,
        endpoint_url=endpoint_url,
        model_name=model_name,
        prompt_text=user_text,
        system_text=system_text,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )
    if not should_retry_strict_json_output(raw_text):
        return raw_text

    logger.warning("Model output was not strict JSON; retrying once with stricter user prompt.")
    return analyze_image_fn(
        image_path,
        endpoint_url=endpoint_url,
        model_name=model_name,
        prompt_text=build_strict_json_retry_user_text(),
        system_text=system_text,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )


def analyze_and_parse_with_strict_json_retry(
    *,
    analyze_image_fn: Callable[..., str],
    parse_output_fn: Callable[..., dict[str, Any]],
    image_path: str,
    system_text: str,
    user_text: str,
    strategy: str,
    endpoint_url: str | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    raw_text = analyze_image_fn(
        image_path,
        endpoint_url=endpoint_url,
        model_name=model_name,
        prompt_text=user_text,
        system_text=system_text,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
    )

    if should_retry_strict_json_output(raw_text):
        logger.warning("Model output was not strict JSON; retrying once with strict retry prompt.")
        raw_text = analyze_image_fn(
            image_path,
            endpoint_url=endpoint_url,
            model_name=model_name,
            prompt_text=build_strict_json_retry_user_text(),
            system_text=system_text,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )

    try:
        return raw_text, parse_output_fn(raw_text, strategy=strategy)
    except ValueError:
        logger.warning("Model output failed JSON parsing; retrying once with strict retry prompt.")
        retry_raw_text = analyze_image_fn(
            image_path,
            endpoint_url=endpoint_url,
            model_name=model_name,
            prompt_text=build_strict_json_retry_user_text(),
            system_text=system_text,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        return retry_raw_text, parse_output_fn(retry_raw_text, strategy=strategy)
