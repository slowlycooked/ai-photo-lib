from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import get_db
from ..models.ai import ProjectAISettings, ProjectPromptTemplate
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.project_ai import (
    PromptTemplateCreate,
    PromptTemplateListResponse,
    PromptTemplateResponse,
    PromptTemplateTestRequest,
    PromptTemplateTestResponse,
    PromptTemplateUpdate,
)
from ..services.json_parser import parse_model_json_output
from ..services.project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    activate_prompt_template,
    analyze_and_parse_with_strict_json_retry,
    build_default_template,
    default_output_schema,
    get_active_prompt_template,
    get_active_prompt_template_strict,
    get_or_create_project_ai_settings,
    get_project_ai_settings_strict,
    render_analysis_prompt_parts,
)
from ..services.vlm_client import VLMRequestError, analyze_image

router = APIRouter(prefix="/projects", tags=["projects-prompt-templates"])


@router.get(
    "/{project_id}/prompt-templates",
    response_model=PromptTemplateListResponse,
)
def list_project_prompt_templates(
    project_id: int,
    task_type: str = TASK_IMAGE_ANALYSIS,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """List all prompt templates for a project and task type."""
    rows = (
        db.query(ProjectPromptTemplate)
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == task_type,
        )
        .order_by(ProjectPromptTemplate.version.desc(), ProjectPromptTemplate.id.desc())
        .all()
    )
    return PromptTemplateListResponse(total=len(rows), items=rows)


@router.post(
    "/{project_id}/prompt-templates",
    response_model=PromptTemplateResponse,
    status_code=201,
)
def create_project_prompt_template(
    project_id: int,
    body: PromptTemplateCreate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Create a new prompt template for a project."""
    latest = (
        db.query(func.max(ProjectPromptTemplate.version))
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == body.task_type,
        )
        .scalar()
    )
    next_version = (latest or 0) + 1

    template = ProjectPromptTemplate(
        project_id=project_id,
        name=body.name,
        task_type=body.task_type,
        system_prompt=body.system_prompt,
        user_prompt=body.user_prompt,
        output_schema=body.output_schema or default_output_schema(),
        is_active=False,
        version=next_version,
    )
    db.add(template)
    db.flush()

    if body.is_active:
        activate_prompt_template(db, project_id, template, task_type=body.task_type)

    db.commit()
    db.refresh(template)
    return template


@router.put(
    "/{project_id}/prompt-templates/{template_id}",
    response_model=PromptTemplateResponse,
)
def update_project_prompt_template(
    project_id: int,
    template_id: int,
    body: PromptTemplateUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Create a new version of an existing prompt template."""
    current = (
        db.query(ProjectPromptTemplate)
        .filter(
            ProjectPromptTemplate.id == template_id,
            ProjectPromptTemplate.project_id == project_id,
        )
        .first()
    )
    if not current:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    next_version = (
        db.query(func.max(ProjectPromptTemplate.version))
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == current.task_type,
        )
        .scalar()
        or 0
    ) + 1

    new_template = ProjectPromptTemplate(
        project_id=project_id,
        name=body.name or current.name,
        task_type=current.task_type,
        system_prompt=(
            body.system_prompt if body.system_prompt is not None else current.system_prompt
        ),
        user_prompt=body.user_prompt,
        output_schema=body.output_schema or current.output_schema or default_output_schema(),
        is_active=False,
        version=next_version,
    )
    db.add(new_template)
    db.flush()

    if body.is_active:
        activate_prompt_template(db, project_id, new_template, task_type=current.task_type)

    db.commit()
    db.refresh(new_template)
    return new_template


@router.delete(
    "/{project_id}/prompt-templates/{template_id}",
    status_code=204,
)
def delete_project_prompt_template(
    project_id: int,
    template_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Delete a non-active prompt template."""
    template = (
        db.query(ProjectPromptTemplate)
        .filter(
            ProjectPromptTemplate.id == template_id,
            ProjectPromptTemplate.project_id == project_id,
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    settings_row = (
        db.query(ProjectAISettings)
        .filter(ProjectAISettings.project_id == project_id)
        .first()
    )
    if template.is_active or (
        settings_row and settings_row.active_prompt_template_id == template.id
    ):
        raise HTTPException(status_code=400, detail="Cannot delete active prompt template")

    db.delete(template)
    db.commit()


@router.post(
    "/{project_id}/prompt-templates/reset-default",
    response_model=PromptTemplateResponse,
)
def reset_project_prompt_template_default(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Create and activate a new default prompt template for a project."""
    next_version = (
        db.query(func.max(ProjectPromptTemplate.version))
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
        )
        .scalar()
        or 0
    ) + 1

    base = build_default_template(project_id)
    template = ProjectPromptTemplate(
        project_id=project_id,
        name=f"默认图片分析模板 v{next_version}",
        task_type=TASK_IMAGE_ANALYSIS,
        system_prompt=base.system_prompt,
        user_prompt=base.user_prompt,
        output_schema=base.output_schema,
        is_active=False,
        version=next_version,
    )
    db.add(template)
    db.flush()
    activate_prompt_template(db, project_id, template, task_type=TASK_IMAGE_ANALYSIS)

    db.commit()
    db.refresh(template)
    return template


@router.post(
    "/{project_id}/prompt-templates/test",
    response_model=PromptTemplateTestResponse,
)
def test_project_prompt_template(
    project_id: int,
    body: PromptTemplateTestRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Test a prompt template against a specific photo using the live VLM."""
    photo = (
        db.query(Photo)
        .filter(Photo.id == body.image_id, Photo.project_id == project_id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found in project")

    try:
        settings_row = get_project_ai_settings_strict(db, project_id)
        template = get_active_prompt_template_strict(
            db,
            project_id,
            task_type=TASK_IMAGE_ANALYSIS,
            template_id=body.prompt_template_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    system_text, user_text = render_analysis_prompt_parts(
        photo=photo,
        prompt_template=template,
        output_language=settings_row.output_language,
        override_prompt=body.override_prompt,
    )

    image_path = photo.thumbnail_path or photo.file_path
    started = time.perf_counter()
    try:
        raw_output, parsed = analyze_and_parse_with_strict_json_retry(
            analyze_image_fn=analyze_image,
            parse_output_fn=parse_model_json_output,
            image_path=image_path,
            endpoint_url=settings_row.endpoint_url,
            model_name=settings_row.model_name,
            system_text=system_text,
            user_text=user_text,
            strategy=settings_row.json_parse_strategy,
            temperature=settings_row.temperature,
            top_p=settings_row.top_p,
            max_tokens=settings_row.max_tokens,
        )
    except VLMRequestError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return PromptTemplateTestResponse(
            success=False,
            raw_output="",
            parsed_json=None,
            error=str(exc),
            retryable=exc.retryable,
            error_code=exc.code,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - started) * 1000)
        return PromptTemplateTestResponse(
            success=False,
            raw_output="",
            parsed_json=None,
            error=str(exc),
            retryable=False,
            error_code="parse_error",
            duration_ms=duration_ms,
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    return PromptTemplateTestResponse(
        success=True,
        raw_output=raw_output,
        parsed_json=parsed,
        error=None,
        retryable=None,
        error_code=None,
        duration_ms=duration_ms,
    )
