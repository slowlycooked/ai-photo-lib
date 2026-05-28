from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..models.project import Project
from ..schemas.project_task import (
    ProjectTaskFailureListResponse,
    ProjectTaskListResponse,
    ProjectTaskResponse,
)
from ..services.project_tasks_app_service import (
    ProjectTaskInvalidTransitionError,
    ProjectTaskNotFoundError,
    ProjectTasksAppService,
)

router = APIRouter(prefix="/projects", tags=["project-tasks"])


@router.get("/{project_id}/tasks", response_model=ProjectTaskListResponse)
def list_project_task_history(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskListResponse:
    return ProjectTasksAppService(db).list_tasks(
        project_id=project.id,
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )


@router.get("/{project_id}/tasks/{task_id}", response_model=ProjectTaskResponse)
def get_project_task_detail(
    task_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskResponse:
    try:
        return ProjectTasksAppService(db).get_task(project_id=project.id, task_id=task_id)
    except ProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{project_id}/tasks/{task_id}/failures", response_model=ProjectTaskFailureListResponse)
def list_project_task_failure_details(
    task_id: int,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskFailureListResponse:
    try:
        return ProjectTasksAppService(db).list_task_failures(
            project_id=project.id,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )
    except ProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/tasks/{task_id}/pause", response_model=ProjectTaskResponse)
def pause_project_task(
    task_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskResponse:
    service = ProjectTasksAppService(db)
    try:
        return service.pause_task(project_id=project.id, task_id=task_id)
    except ProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectTaskInvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{project_id}/tasks/{task_id}/cancel", response_model=ProjectTaskResponse)
def cancel_project_task(
    task_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskResponse:
    service = ProjectTasksAppService(db)
    try:
        return service.cancel_task(project_id=project.id, task_id=task_id)
    except ProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectTaskInvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{project_id}/tasks/{task_id}/resume", response_model=ProjectTaskResponse)
def resume_paused_project_task(
    task_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> ProjectTaskResponse:
    service = ProjectTasksAppService(db)
    try:
        return service.resume_task(project_id=project.id, task_id=task_id)
    except ProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProjectTaskInvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
