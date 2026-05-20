from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, time as time_
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models.ai import AIJob, PhotoAIAnalysis, ProjectPromptTemplate
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.project_ai import (
    ProjectAISettingsResponse,
    ProjectAISettingsUpdate,
    PromptTemplateCreate,
    PromptTemplateListResponse,
    PromptTemplateResponse,
    PromptTemplateTestRequest,
    PromptTemplateTestResponse,
    PromptTemplateUpdate,
)
from ..schemas.ai import (
    AIAnalysisResponse,
    AIJobListResponse,
    AIJobResponse,
    AIStatusResponse,
    RetryFailedResponse,
    StartAnalysisResponse,
)
from ..services.json_parser import parse_model_json_output
from ..services.project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    activate_prompt_template,
    build_default_template,
    default_output_schema,
    get_active_prompt_template,
    get_or_create_project_ai_settings,
    render_analysis_prompt,
)
from ..services.vlm_client import VLMRequestError, analyze_image
from ..schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from ..schemas.photo import PhotoDetailResponse, PhotoListResponse
from ..schemas.scan import ScanStatus
from ..schemas.search import SearchResponse
from ..services.folder_service import apply_folder_filter
from ..services.scanner import get_project_scan_state, scan_project
from ..services.search_service import search_photos
from ..services.thumbnail import generate_thumbnail

router = APIRouter(prefix="/projects", tags=["projects"])


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
def list_projects(db: Session = Depends(get_db)):
    projects = (
        db.query(Project)
        .filter(Project.deleted_at.is_(None))
        .order_by(Project.is_default.desc(), Project.created_at.asc())
        .all()
    )
    return ProjectListResponse(total=len(projects), items=projects)


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    # If this is being set as default, unset others
    if body.is_default:
        db.query(Project).filter(Project.deleted_at.is_(None)).update(
            {"is_default": False}
        )

    thumbnail = body.thumbnail_path or settings.thumbnail_path
    project = Project(
        name=body.name,
        description=body.description,
        photo_library_path=body.photo_library_path,
        thumbnail_path=thumbnail,
        is_default=body.is_default,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int, body: ProjectUpdate, db: Session = Depends(get_db)
):
    project = _get_or_404(db, project_id)

    if body.is_default is True:
        db.query(Project).filter(
            Project.deleted_at.is_(None), Project.id != project_id
        ).update({"is_default": False})

    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    if body.photo_library_path is not None:
        project.photo_library_path = body.photo_library_path
    if body.thumbnail_path is not None:
        project.thumbnail_path = body.thumbnail_path
    if body.is_default is not None:
        project.is_default = body.is_default

    project.updated_at = datetime.now()
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    if project.is_default:
        raise HTTPException(
            status_code=400, detail="Cannot delete the default project"
        )
    project.deleted_at = datetime.now()
    db.commit()


# ─── Scan ────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/scan/start")
def start_project_scan(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    state = get_project_scan_state(project_id)
    if state["running"]:
        return {"message": "Scan already in progress", "status": ScanStatus(**state)}

    def _run():
        sess = SessionLocal()
        try:
            scan_project(sess, project_id)
        finally:
            sess.close()

    thread = threading.Thread(
        target=_run, daemon=True, name=f"scanner-project-{project_id}"
    )
    thread.start()
    return {"message": "Scan started", "status": ScanStatus(**state)}


@router.get("/{project_id}/scan/status", response_model=ScanStatus)
def get_project_scan_status(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    return ScanStatus(**get_project_scan_state(project_id))


# ─── AI ──────────────────────────────────────────────────────────────────────

@router.post("/{project_id}/ai/analyze/start", response_model=StartAnalysisResponse)
def start_project_ai(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)

    active_photo_ids = (
        db.query(AIJob.photo_id)
        .filter(AIJob.status.in_(["queued", "running"]))
        .subquery()
    )
    analyzed_photo_ids = db.query(PhotoAIAnalysis.photo_id).subquery()

    photos_to_process = (
        db.query(Photo)
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.id.not_in(active_photo_ids),
            Photo.id.not_in(analyzed_photo_ids),
        )
        .all()
    )

    count = 0
    for photo in photos_to_process:
        db.add(
            AIJob(
                photo_id=photo.id,
                project_id=project_id,
                job_type="analyze",
                status="queued",
            )
        )
        count += 1

    db.commit()
    return StartAnalysisResponse(created_jobs=count, message="AI analysis jobs created")


@router.get("/{project_id}/ai/status", response_model=AIStatusResponse)
def get_project_ai_status(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)

    rows = (
        db.query(AIJob.status, func.count(AIJob.id))
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id)
        .group_by(AIJob.status)
        .all()
    )
    counts: dict[str, int] = {status: cnt for status, cnt in rows}
    total = sum(counts.values())
    return AIStatusResponse(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        total=total,
    )


@router.get("/{project_id}/ai/jobs", response_model=AIJobListResponse)
def list_project_ai_jobs(
    project_id: int,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)
    limit = max(1, min(limit, 200))
    query = (
        db.query(AIJob, Photo.file_name)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id)
    )
    if status:
        query = query.filter(AIJob.status == status)

    total = query.count()
    rows = query.order_by(AIJob.created_at.desc()).offset(offset).limit(limit).all()

    items = [
        AIJobResponse(
            id=job.id,
            photo_id=job.photo_id,
            job_type=job.job_type,
            status=job.status,
            retry_count=job.retry_count,
            error_message=job.error_message,
            prompt_template_id=job.prompt_template_id,
            prompt_version=job.prompt_version,
            model_name=job.model_name,
            model_params=job.model_params,
            raw_model_output=job.raw_model_output,
            parse_error=job.parse_error,
            started_at=job.started_at,
            finished_at=job.finished_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
            file_name=file_name,
        )
        for job, file_name in rows
    ]
    return AIJobListResponse(total=total, items=items)


@router.post("/{project_id}/ai/jobs/retry-failed", response_model=RetryFailedResponse)
def retry_project_failed_jobs(project_id: int, db: Session = Depends(get_db)):
    from datetime import timezone

    _get_or_404(db, project_id)
    jobs = (
        db.query(AIJob)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(
            Photo.project_id == project_id,
            AIJob.status == "failed",
            AIJob.retry_count < settings.ai_max_retries,
        )
        .all()
    )
    now = datetime.now(timezone.utc)
    count = 0
    for job in jobs:
        job.status = "queued"
        job.error_message = None
        job.updated_at = now
        count += 1
    db.commit()
    return RetryFailedResponse(retried_jobs=count, message="Failed jobs re-queued")


@router.delete("/{project_id}/ai/jobs/failed", response_model=dict)
def clear_project_failed_jobs(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    failed = (
        db.query(AIJob)
        .join(Photo, AIJob.photo_id == Photo.id)
        .filter(Photo.project_id == project_id, AIJob.status == "failed")
    )
    count = failed.count()
    # Collect IDs to delete without touching cross-table state
    ids = [job.id for job in failed.all()]
    if ids:
        db.query(AIJob).filter(AIJob.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"deleted_jobs": count, "message": "Failed jobs cleared"}


@router.get("/{project_id}/ai-settings", response_model=ProjectAISettingsResponse)
def get_project_ai_settings(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)
    row = get_or_create_project_ai_settings(db, project_id)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{project_id}/ai-settings", response_model=ProjectAISettingsResponse)
def update_project_ai_settings(
    project_id: int,
    body: ProjectAISettingsUpdate,
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)
    row = get_or_create_project_ai_settings(db, project_id)

    row.provider = body.provider
    row.endpoint_url = body.endpoint_url
    row.model_name = body.model_name
    row.temperature = body.temperature
    row.top_p = body.top_p
    row.max_tokens = body.max_tokens
    row.retry_count = body.retry_count
    row.output_language = body.output_language
    row.json_parse_strategy = body.json_parse_strategy
    row.updated_at = datetime.now()

    if body.active_prompt_template_id is not None:
        template = (
            db.query(ProjectPromptTemplate)
            .filter(
                ProjectPromptTemplate.id == body.active_prompt_template_id,
                ProjectPromptTemplate.project_id == project_id,
                ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
            )
            .first()
        )
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        activate_prompt_template(db, project_id, template, task_type=TASK_IMAGE_ANALYSIS)

    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/{project_id}/prompt-templates",
    response_model=PromptTemplateListResponse,
)
def list_project_prompt_templates(
    project_id: int,
    task_type: str = TASK_IMAGE_ANALYSIS,
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)
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
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)

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
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)
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


@router.post(
    "/{project_id}/prompt-templates/reset-default",
    response_model=PromptTemplateResponse,
)
def reset_project_prompt_template_default(
    project_id: int,
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)

    next_version = (
        db.query(func.max(ProjectPromptTemplate.version))
        .filter(
            ProjectPromptTemplate.project_id == project_id,
            ProjectPromptTemplate.task_type == TASK_IMAGE_ANALYSIS,
        )
        .scalar()
        or 0
    ) + 1

    # Build the template from the shared default in project_ai_service so that
    # the reset-default operation always reflects the service-level default and
    # not any business-specific text hardcoded in this router.
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
    db: Session = Depends(get_db),
):
    _get_or_404(db, project_id)

    photo = (
        db.query(Photo)
        .filter(Photo.id == body.image_id, Photo.project_id == project_id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found in project")

    settings_row = get_or_create_project_ai_settings(db, project_id)
    template = get_active_prompt_template(
        db,
        project_id,
        task_type=TASK_IMAGE_ANALYSIS,
        template_id=body.prompt_template_id,
    )

    prompt = render_analysis_prompt(
        photo=photo,
        prompt_template=template,
        output_language=settings_row.output_language,
        override_prompt=body.override_prompt,
    )

    image_path = photo.thumbnail_path or photo.file_path
    started = time.perf_counter()
    try:
        raw_output = analyze_image(
            image_path,
            endpoint_url=settings_row.endpoint_url,
            model_name=settings_row.model_name,
            prompt_text=prompt,
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

    duration_ms = int((time.perf_counter() - started) * 1000)

    try:
        parsed = parse_model_json_output(
            raw_output,
            strategy=settings_row.json_parse_strategy,
        )
        return PromptTemplateTestResponse(
            success=True,
            raw_output=raw_output,
            parsed_json=parsed,
            error=None,
            retryable=None,
            error_code=None,
            duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001
        return PromptTemplateTestResponse(
            success=False,
            raw_output=raw_output,
            parsed_json=None,
            error=str(exc),
            retryable=False,
            error_code="parse_error",
            duration_ms=duration_ms,
        )


# ─── Photos ───────────────────────────────────────────────────────────────────

@router.get("/{project_id}/photos", response_model=PhotoListResponse)
def list_project_photos(
    project_id: int,
    page: int = 1,
    page_size: int = Query(50, ge=1, le=100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    """List photos for a specific project."""
    _get_or_404(db, project_id)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    base_query = db.query(Photo).filter(
        Photo.project_id == project_id, Photo.deleted_at.is_(None)
    )
    if date_from is not None:
        base_query = base_query.filter(
            Photo.taken_at >= datetime.combine(date_from, time_.min)
        )
    if date_to is not None:
        base_query = base_query.filter(
            Photo.taken_at < datetime.combine(date_to, time_.min)
        )
    if folder_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    total = base_query.count()
    photos = (
        base_query
        .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return PhotoListResponse(total=total, page=page, page_size=page_size, items=photos)


@router.get("/{project_id}/photos/timeline")
def get_project_timeline(
    project_id: int,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    """Get monthly photo count timeline for a specific project."""
    _get_or_404(db, project_id)
    base_query = db.query(Photo).filter(
        Photo.project_id == project_id,
        Photo.deleted_at.is_(None),
        Photo.taken_at.is_not(None),
    )
    if folder_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    rows = (
        base_query
        .with_entities(
            extract("year", Photo.taken_at).label("year"),
            extract("month", Photo.taken_at).label("month"),
            func.count(Photo.id).label("count"),
        )
        .group_by("year", "month")
        .order_by(
            extract("year", Photo.taken_at).desc(),
            extract("month", Photo.taken_at).desc(),
        )
        .all()
    )
    return {
        "items": [
            {
                "key": f"{int(r.year)}-{str(int(r.month)).zfill(2)}",
                "year": int(r.year),
                "month": int(r.month),
                "count": r.count,
            }
            for r in rows
        ]
    }


@router.get("/{project_id}/photos/{photo_id}", response_model=PhotoDetailResponse)
def get_project_photo(
    project_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
):
    """Get a single photo within project scope."""
    _get_or_404(db, project_id)
    return _get_project_photo_or_404(db, project_id, photo_id)


@router.get("/{project_id}/photos/{photo_id}/thumbnail")
def get_project_photo_thumbnail(
    project_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
):
    """Get a photo thumbnail within project scope."""
    project = _get_or_404(db, project_id)
    photo = _get_project_photo_or_404(db, project_id, photo_id)

    if not photo.thumbnail_path or not os.path.exists(photo.thumbnail_path):
        if not os.path.exists(photo.file_path):
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        thumb = generate_thumbnail(
            photo.file_path,
            project_id=project_id,
            thumbnail_root=project.thumbnail_path,
        )
        if not thumb:
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        photo.thumbnail_path = thumb
        db.commit()

    return FileResponse(
        photo.thumbnail_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@router.get("/{project_id}/photos/{photo_id}/original")
def get_project_photo_original(
    project_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
):
    """Download original file within project scope."""
    _get_or_404(db, project_id)
    photo = _get_project_photo_or_404(db, project_id, photo_id)

    if not os.path.exists(photo.file_path):
        raise HTTPException(status_code=404, detail="Original file not found on disk")

    return FileResponse(
        photo.file_path,
        media_type=photo.mime_type or "application/octet-stream",
        filename=photo.file_name,
        headers={
            "Cache-Control": "private, max-age=0",
            "Content-Disposition": f'attachment; filename="{photo.file_name}"',
        },
    )


@router.get("/{project_id}/photos/{photo_id}/ai", response_model=AIAnalysisResponse)
def get_project_photo_ai(
    project_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
):
    """Get latest AI analysis within project scope."""
    _get_or_404(db, project_id)
    _get_project_photo_or_404(db, project_id, photo_id)

    analysis = (
        db.query(PhotoAIAnalysis)
        .filter(
            PhotoAIAnalysis.photo_id == photo_id,
            PhotoAIAnalysis.project_id == project_id,
        )
        .order_by(PhotoAIAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No AI analysis found for this photo")
    return analysis


# ─── Search ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/search", response_model=SearchResponse)
def project_search(
    project_id: int,
    q: str,
    page: int = 1,
    page_size: int = 50,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    """Search photos within a specific project."""
    _get_or_404(db, project_id)
    total, items = search_photos(
        db, q, page=page, page_size=page_size,
        project_id=project_id, folder_id=folder_id, folder_scope=folder_scope,
    )
    return SearchResponse(query=q, total=total, page=page, page_size=page_size, items=items)


# ─── Tags ─────────────────────────────────────────────────────────────────────

from sqlalchemy import text as _sa_text
from pydantic import BaseModel as _BaseModel


class _TagCount(_BaseModel):
    tag: str
    count: int


class _TagsResponse(_BaseModel):
    scene_tags: list[_TagCount]
    object_tags: list[_TagCount]
    activity_tags: list[_TagCount]
    quality_tags: list[_TagCount]
    search_keywords: list[_TagCount]


def _count_tags(db: Session, field: str, project_id: int, limit: int = 100) -> list[_TagCount]:
    sql = _sa_text(
        f"SELECT unnest(paa.{field}) AS tag, COUNT(*) AS cnt "
        f"FROM photo_ai_analysis paa "
        f"WHERE paa.project_id = :pid AND paa.{field} IS NOT NULL "
        f"GROUP BY tag ORDER BY cnt DESC LIMIT :limit"
    )
    rows = db.execute(sql, {"pid": project_id, "limit": limit}).fetchall()
    return [_TagCount(tag=r[0], count=r[1]) for r in rows]


@router.get("/{project_id}/tags", response_model=_TagsResponse)
def project_tags(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Get tag counts for a specific project."""
    _get_or_404(db, project_id)
    return _TagsResponse(
        scene_tags=_count_tags(db, "scene_tags", project_id),
        object_tags=_count_tags(db, "object_tags", project_id),
        activity_tags=_count_tags(db, "activity_tags", project_id),
        quality_tags=_count_tags(db, "quality_tags", project_id),
        search_keywords=_count_tags(db, "search_keywords", project_id),
    )


# ─── Helper ──────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, project_id: int) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _get_project_photo_or_404(db: Session, project_id: int, photo_id: int) -> Photo:
    photo = (
        db.query(Photo)
        .filter(
            Photo.id == photo_id,
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found in project")
    return photo
