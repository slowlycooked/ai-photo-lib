from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project, require_project_manager
from ..models.project import Project
from ..schemas.scan import ScanStatus
from ..services.project_task_service import (
    SCAN_TASK_TYPES,
    TASK_TYPE_LIBRARY_REINDEX,
    TASK_TYPE_LIBRARY_SCAN,
    build_scan_status,
    enqueue_scan_task,
    get_active_scan_task,
    get_latest_scan_task,
    request_project_task_cancel,
)
from ..services.project_scan_runtime_service import validate_project_library_path

router = APIRouter(prefix="/projects", tags=["projects-scan"])


@router.post("/{project_id}/scan/start")
def start_project_scan(
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Queue a project library scan for the worker to execute."""
    library_error = validate_project_library_path(project.photo_library_path)
    if library_error:
        raise HTTPException(status_code=422, detail=library_error)

    project_id = project.id
    result = enqueue_scan_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_LIBRARY_SCAN,
        request_params={},
    )
    return {
        "message": "Scan queued" if result.created else "Scan already in progress",
        "status": build_scan_status(result.task),
    }


@router.get("/{project_id}/scan/status", response_model=ScanStatus)
def get_project_scan_status(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return the current persisted scan/reindex task state for a project."""
    active_task = get_active_scan_task(db, project.id)
    if active_task is not None:
        return build_scan_status(active_task)
    return build_scan_status(get_latest_scan_task(db, project.id))


@router.post("/{project_id}/scan/cancel", response_model=ScanStatus)
def cancel_project_scan(
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Request cancellation for the active project scan/reindex task."""
    task = request_project_task_cancel(
        db,
        project_id=project.id,
        task_types=SCAN_TASK_TYPES,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="No active scan/reindex task")
    return build_scan_status(task)


class _ReindexScope(str, Enum):
    all = "all"
    missing_metadata = "missing_metadata"
    missing_location = "missing_location"


@router.post("/{project_id}/scan/reindex")
def start_project_reindex(
    scope: _ReindexScope = _ReindexScope.missing_metadata,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Queue a metadata reindex task for the worker to execute."""
    library_error = validate_project_library_path(project.photo_library_path)
    if library_error:
        raise HTTPException(status_code=422, detail=library_error)

    project_id = project.id
    result = enqueue_scan_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_LIBRARY_REINDEX,
        request_params={"scope": scope.value},
    )
    return {
        "message": "Reindex queued" if result.created else "Scan/reindex already in progress",
        "status": build_scan_status(result.task),
    }
