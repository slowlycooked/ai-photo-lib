from __future__ import annotations

import threading
from enum import Enum

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import SessionLocal, get_db
from ..models.project import Project
from ..schemas.scan import ScanStatus
from ..services.scanner import get_project_scan_state, reindex_project, scan_project

router = APIRouter(prefix="/projects", tags=["projects-scan"])


@router.post("/{project_id}/scan/start")
def start_project_scan(project: Project = Depends(require_project)):
    """Start an async scan for a project's photo library."""
    project_id = project.id
    state = get_project_scan_state(project_id)
    if state["running"]:
        return {"message": "Scan already in progress", "status": ScanStatus(**state)}

    def _run() -> None:
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
def get_project_scan_status(project: Project = Depends(require_project)):
    """Return the current scan state for a project."""
    return ScanStatus(**get_project_scan_state(project.id))


class _ReindexScope(str, Enum):
    all = "all"
    missing_metadata = "missing_metadata"
    missing_location = "missing_location"


@router.post("/{project_id}/scan/reindex")
def start_project_reindex(
    scope: _ReindexScope = _ReindexScope.missing_metadata,
    project: Project = Depends(require_project),
):
    """Re-extract EXIF metadata for photos already in the DB.

    scope=missing_metadata (default): only photos where taken_at IS NULL
    scope=missing_location: only photos where GPS exists but place fields are empty
    scope=all: every photo in the project
    """
    project_id = project.id
    state = get_project_scan_state(project_id)
    if state["running"]:
        return {"message": "Scan/reindex already in progress", "status": ScanStatus(**state)}

    def _run() -> None:
        sess = SessionLocal()
        try:
            reindex_project(sess, project_id, scope=scope.value)
        finally:
            sess.close()

    thread = threading.Thread(
        target=_run, daemon=True, name=f"reindex-project-{project_id}"
    )
    thread.start()
    return {"message": "Reindex started", "status": ScanStatus(**state)}
