from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models.ai import AIJob, PhotoAIAnalysis
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.ai import AIStatusResponse, StartAnalysisResponse
from ..schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from ..schemas.scan import ScanStatus
from ..services.scanner import get_project_scan_state, scan_project

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
        db.add(AIJob(photo_id=photo.id, job_type="analyze", status="queued"))
        count += 1

    db.commit()
    return StartAnalysisResponse(created_jobs=count, message="AI analysis jobs created")


@router.get("/{project_id}/ai/status", response_model=AIStatusResponse)
def get_project_ai_status(project_id: int, db: Session = Depends(get_db)):
    _get_or_404(db, project_id)

    # Only count jobs for photos in this project
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
