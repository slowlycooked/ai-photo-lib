from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..schemas.project_task import (
    ProjectTaskFailureDetail,
    ProjectTaskFailureListResponse,
    ProjectTaskListResponse,
    ProjectTaskResponse,
)
from .project_task_service import (
    extract_task_failures,
    extract_task_recent_errors,
    get_project_task,
    list_project_task_failures,
    list_project_tasks,
    request_project_task_cancel_by_id,
    request_project_task_pause,
    resume_project_task,
)


class ProjectTaskNotFoundError(RuntimeError):
    pass


class ProjectTaskInvalidTransitionError(RuntimeError):
    pass


@dataclass
class ProjectTasksAppService:
    db: Session

    def list_tasks(
        self,
        *,
        project_id: int,
        status: Optional[str],
        task_type: Optional[str],
        limit: int,
        offset: int,
    ) -> ProjectTaskListResponse:
        total, items = list_project_tasks(
            self.db,
            project_id=project_id,
            status=status,
            task_type=task_type,
            limit=limit,
            offset=offset,
        )
        return ProjectTaskListResponse(
            total=total,
            items=[self._build_task_response(item) for item in items],
        )

    def get_task(self, *, project_id: int, task_id: int) -> ProjectTaskResponse:
        task = get_project_task(self.db, project_id=project_id, task_id=task_id)
        if task is None:
            raise ProjectTaskNotFoundError("Project task not found")
        return self._build_task_response(task)

    def list_task_failures(
        self,
        *,
        project_id: int,
        task_id: int,
        limit: int,
        offset: int,
    ) -> ProjectTaskFailureListResponse:
        result = list_project_task_failures(
            self.db,
            project_id=project_id,
            task_id=task_id,
            limit=limit,
            offset=offset,
        )
        if result is None:
            raise ProjectTaskNotFoundError("Project task not found")
        total, items = result
        return ProjectTaskFailureListResponse(
            total=total,
            items=[ProjectTaskFailureDetail.model_validate(item) for item in items],
        )

    def pause_task(self, *, project_id: int, task_id: int) -> ProjectTaskResponse:
        task = request_project_task_pause(self.db, project_id=project_id, task_id=task_id)
        if task is None:
            raise ProjectTaskNotFoundError("Project task not found")
        if task.status not in ("paused", "running"):
            raise ProjectTaskInvalidTransitionError(
                f"Task cannot be paused from {task.status}"
            )
        return self._build_task_response(task)

    def cancel_task(self, *, project_id: int, task_id: int) -> ProjectTaskResponse:
        task = request_project_task_cancel_by_id(self.db, project_id=project_id, task_id=task_id)
        if task is None:
            raise ProjectTaskNotFoundError("Project task not found")
        if task.status not in ("cancelled", "running"):
            raise ProjectTaskInvalidTransitionError(
                f"Task cannot be cancelled from {task.status}"
            )
        return self._build_task_response(task)

    def resume_task(self, *, project_id: int, task_id: int) -> ProjectTaskResponse:
        task = resume_project_task(self.db, project_id=project_id, task_id=task_id)
        if task is None:
            raise ProjectTaskNotFoundError("Project task not found")
        if task.status != "queued":
            raise ProjectTaskInvalidTransitionError(
                f"Task cannot be resumed from {task.status}"
            )
        return self._build_task_response(task)

    @staticmethod
    def _build_task_response(task) -> ProjectTaskResponse:
        failures = extract_task_failures(task)
        return ProjectTaskResponse.model_validate(
            {
                **task.__dict__,
                "recent_errors": extract_task_recent_errors(task),
                "failure_count": len(failures),
                "latest_failure": failures[0] if failures else None,
            }
        )