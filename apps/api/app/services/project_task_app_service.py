from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.project_task import ProjectTask
from .task_claim_service import TaskClaimService
from .project_task_handlers import (
    ProjectTaskHandler,
    ProjectTaskRunContext,
    build_default_project_task_handlers,
)
from .project_task_service import (
    build_queued_progress_payload,
    empty_project_task_state,
)

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 12000


class ProjectTaskCancelled(RuntimeError):
    pass


class ProjectTaskPaused(RuntimeError):
    pass


class ProjectTaskAppService:
    def __init__(
        self,
        db: Session,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        handlers: Optional[Mapping[str, ProjectTaskHandler]] = None,
    ) -> None:
        self._db = db
        self._session_factory = session_factory
        self._handlers = dict(handlers or build_default_project_task_handlers())
        self._claim_service = TaskClaimService(db)

    def process_task(self, task: ProjectTask) -> None:
        now = datetime.now(timezone.utc)
        if self._cancel_requested(task):
            self._persist_cancelled(task.id)
            return
        if self._pause_requested(task):
            self._persist_paused(task.id)
            return

        if task.status != "running":
            task.status = "running"
            task.started_at = now
            task.updated_at = now
            task.progress_payload = build_queued_progress_payload(
                task.task_type,
                task.request_params,
                project_id=task.project_id,
            )
            self._claim_service.touch_project_task_lease(task)
            self._db.commit()

        try:
            final_state = self._run_task(task)

            self._db.refresh(task)
            if self._cancel_requested(task):
                self._persist_cancelled(task.id, final_state)
                return
            if self._pause_requested(task):
                self._persist_paused(task.id, final_state)
                return

            final_errors = int(final_state.get("errors") or 0)
            task.status = "completed_with_errors" if final_errors > 0 else "success"
            task.error_message = None
            task.progress_payload = dict(final_state)
            task.result_payload = dict(final_state)
            task.finished_at = datetime.now(timezone.utc)
            task.updated_at = task.finished_at
            task.locked_by = None
            task.locked_at = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            self._db.commit()
        except ProjectTaskCancelled:
            self._db.rollback()
            self._persist_cancelled(task.id)
        except ProjectTaskPaused:
            self._db.rollback()
            self._persist_paused(task.id)
        except Exception as exc:  # noqa: BLE001
            self._db.rollback()
            logger.exception(
                "Project task failed. task_id=%s project_id=%s task_type=%s",
                task.id,
                task.project_id,
                task.task_type,
            )
            self._persist_failure(task.id, str(exc))

    def _persist_progress(self, task_id: int, state: dict) -> None:
        with self._session_factory() as db:
            task = self._load_task(db, task_id)
            if task is None:
                return
            if self._cancel_requested(task):
                raise ProjectTaskCancelled()
            if self._pause_requested(task):
                raise ProjectTaskPaused()
            task.progress_payload = dict(state)
            task.updated_at = datetime.now(timezone.utc)
            TaskClaimService(db).touch_project_task_lease(task)
            db.commit()

    def _persist_cancelled(self, task_id: int, state: Optional[dict] = None) -> None:
        with self._session_factory() as db:
            task = self._load_task(db, task_id)
            if task is None:
                return
            progress = dict(
                state
                or task.progress_payload
                or empty_project_task_state(
                    task.task_type,
                    task.request_params,
                    project_id=task.project_id,
                )
            )
            progress["running"] = False
            progress["cancel_requested"] = True
            progress["message"] = "cancelled"
            task.status = "cancelled"
            task.progress_payload = progress
            task.result_payload = progress
            task.error_message = None
            task.finished_at = datetime.now(timezone.utc)
            task.updated_at = task.finished_at
            task.locked_by = None
            task.locked_at = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            db.commit()

    def _persist_paused(self, task_id: int, state: Optional[dict] = None) -> None:
        with self._session_factory() as db:
            task = self._load_task(db, task_id)
            if task is None:
                return
            progress = dict(
                state
                or task.progress_payload
                or empty_project_task_state(
                    task.task_type,
                    task.request_params,
                    project_id=task.project_id,
                )
            )
            progress["running"] = False
            progress["pause_requested"] = True
            progress["message"] = "paused"
            task.status = "paused"
            task.progress_payload = progress
            task.result_payload = progress
            task.error_message = None
            task.updated_at = datetime.now(timezone.utc)
            task.locked_by = None
            task.locked_at = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            db.commit()

    def _persist_failure(self, task_id: int, error_message: str) -> None:
        with self._session_factory() as db:
            task = self._load_task(db, task_id)
            if task is None:
                return
            task.retry_count = int(task.retry_count or 0) + 1
            task.status = "failed"
            task.error_message = error_message[:_MAX_ERROR_LEN]
            task.finished_at = datetime.now(timezone.utc)
            task.updated_at = task.finished_at
            task.last_error_code = "task_failed"
            task.last_error_at = task.finished_at
            task.locked_by = None
            task.locked_at = None
            task.heartbeat_at = None
            task.lease_expires_at = None
            progress = dict(
                task.progress_payload
                or empty_project_task_state(
                    task.task_type,
                    task.request_params,
                    project_id=task.project_id,
                )
            )
            progress["running"] = False
            progress["errors"] = max(int(progress.get("errors") or 0), 1)
            recent_errors = list(progress.get("recent_errors") or [])
            if error_message and error_message not in recent_errors:
                recent_errors.append(error_message[:_MAX_ERROR_LEN])
            progress["recent_errors"] = recent_errors
            task.progress_payload = progress
            db.commit()

    def _run_task(self, task: ProjectTask) -> dict:
        if self._cancel_requested(task):
            raise ProjectTaskCancelled()
        if self._pause_requested(task):
            raise ProjectTaskPaused()
        handler = self._handlers.get(task.task_type)
        if handler is None:
            raise RuntimeError(f"Unsupported project task type: {task.task_type}")
        return handler.run(
            task,
            ProjectTaskRunContext(
                db=self._db,
                persist_progress=self._persist_progress,
            ),
        )

    @staticmethod
    def _load_task(db: Session, task_id: int) -> Optional[ProjectTask]:
        return db.query(ProjectTask).filter(ProjectTask.id == task_id).first()

    @staticmethod
    def _cancel_requested(task: ProjectTask) -> bool:
        progress = task.progress_payload or {}
        return bool(progress.get("cancel_requested"))

    @staticmethod
    def _pause_requested(task: ProjectTask) -> bool:
        progress = task.progress_payload or {}
        return bool(progress.get("pause_requested"))
