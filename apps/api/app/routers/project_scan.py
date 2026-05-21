from __future__ import annotations

import threading

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..database import SessionLocal, get_db
from ..models.project import Project
from ..schemas.scan import ScanStatus
from ..services.scanner import get_project_scan_state, scan_project

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
