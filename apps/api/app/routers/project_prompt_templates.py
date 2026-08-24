from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_manager
from ..database import get_db
from ..models.ai import ProjectPromptTemplate
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
    analyze_and_parse_with_strict_json_retry,
    get_active_prompt_template,
    get_active_prompt_template_strict,
    render_analysis_prompt_parts,
    resolve_project_ai_runtime_settings,
)
from ..services.project_prompt_templates_app_service import (
    ActivePromptTemplateDeleteError,
    ProjectPromptTemplatesAppService,
    PromptTemplateNotFoundError,
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
    rows = ProjectPromptTemplatesAppService(db).list_templates(
        project_id=project_id,
        task_type=task_type,
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
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Create a new prompt template for a project."""
    return ProjectPromptTemplatesAppService(db).create_template(
        project_id=project_id,
        body=body,
    )


@router.put(
    "/{project_id}/prompt-templates/{template_id}",
    response_model=PromptTemplateResponse,
)
def update_project_prompt_template(
    project_id: int,
    template_id: int,
    body: PromptTemplateUpdate,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Create a new version of an existing prompt template."""
    service = ProjectPromptTemplatesAppService(db)
    try:
        return service.update_template(
            project_id=project_id,
            template_id=template_id,
            body=body,
        )
    except PromptTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/{project_id}/prompt-templates/{template_id}",
    status_code=204,
)
def delete_project_prompt_template(
    project_id: int,
    template_id: int,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Delete a non-active prompt template."""
    service = ProjectPromptTemplatesAppService(db)
    try:
        service.delete_template(project_id=project_id, template_id=template_id)
    except PromptTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActivePromptTemplateDeleteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{project_id}/prompt-templates/reset-default",
    response_model=PromptTemplateResponse,
)
def reset_project_prompt_template_default(
    project_id: int,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Create and activate a new default prompt template for a project."""
    return ProjectPromptTemplatesAppService(db).reset_default_template(project_id=project_id)


@router.post(
    "/{project_id}/prompt-templates/test",
    response_model=PromptTemplateTestResponse,
)
def test_project_prompt_template(
    project_id: int,
    body: PromptTemplateTestRequest,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Test a prompt template against a specific photo using the live VLM."""
    photo = ProjectPromptTemplatesAppService(db).get_project_photo(
        project_id=project_id,
        photo_id=body.image_id,
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found in project")

    try:
        runtime_settings = resolve_project_ai_runtime_settings(db, project_id)
        template = get_active_prompt_template_strict(
            db,
            project_id,
            task_type=TASK_IMAGE_ANALYSIS,
            template_id=body.prompt_template_id or runtime_settings.get("active_prompt_template_id"),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    system_text, user_text = render_analysis_prompt_parts(
        photo=photo,
        prompt_template=template,
        output_language=runtime_settings["output_language"],
        override_prompt=body.override_prompt,
    )

    image_path = photo.thumbnail_path or photo.file_path
    started = time.perf_counter()
    try:
        raw_output, parsed = analyze_and_parse_with_strict_json_retry(
            analyze_image_fn=analyze_image,
            parse_output_fn=parse_model_json_output,
            image_path=image_path,
            provider=runtime_settings["provider"],
            endpoint_url=runtime_settings["endpoint_url"],
            model_name=runtime_settings["model_name"],
            system_text=system_text,
            user_text=user_text,
            strategy=runtime_settings["json_parse_strategy"],
            temperature=runtime_settings["temperature"],
            top_p=runtime_settings["top_p"],
            max_tokens=runtime_settings["max_tokens"],
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
