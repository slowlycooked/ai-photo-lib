from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models.project_task import ProjectTask
from .face_scan_batch_service import FaceScanBatchService
from .face_rematch_service import rematch_unknown_faces
from .project_task_service import (
    TASK_TYPE_FACE_SCAN_PROJECT,
    TASK_TYPE_FACE_REMATCH_UNKNOWN,
    TASK_TYPE_LIBRARY_REINDEX,
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
    build_face_cluster_result_payload,
    build_face_rematch_result_payload,
    build_face_scan_project_result_payload,
    build_queued_progress_payload,
    empty_project_task_state,
)
from .scanner import reindex_project, scan_project
from .unknown_face_clustering_service import cluster_unknown_faces

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
    ) -> None:
        self._db = db
        self._session_factory = session_factory

    def process_task(self, task: ProjectTask) -> None:
        now = datetime.now(timezone.utc)
        if self._cancel_requested(task):
            self._persist_cancelled(task.id)
            return
        if self._pause_requested(task):
            self._persist_paused(task.id)
            return

        task.status = "running"
        task.started_at = now
        task.updated_at = now
        task.progress_payload = build_queued_progress_payload(
            task.task_type,
            task.request_params,
            project_id=task.project_id,
        )
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
        if task.task_type == TASK_TYPE_LIBRARY_SCAN:
            return self._run_library_scan(task)
        if task.task_type == TASK_TYPE_LIBRARY_REINDEX:
            return self._run_library_reindex(task)
        if task.task_type == TASK_TYPE_UNKNOWN_FACE_CLUSTERING:
            return self._run_unknown_face_clustering(task)
        if task.task_type == TASK_TYPE_FACE_SCAN_PROJECT:
            return self._run_face_scan_project(task)
        if task.task_type == TASK_TYPE_FACE_REMATCH_UNKNOWN:
            return self._run_face_rematch_unknown(task)
        raise RuntimeError(f"Unsupported project task type: {task.task_type}")

    def _run_library_scan(self, task: ProjectTask) -> dict:
        return scan_project(
            self._db,
            task.project_id,
            progress_callback=lambda state: self._persist_progress(task.id, state),
        )

    def _run_library_reindex(self, task: ProjectTask) -> dict:
        scope = str((task.request_params or {}).get("scope") or "missing_metadata")
        return reindex_project(
            self._db,
            task.project_id,
            scope=scope,
            progress_callback=lambda state: self._persist_progress(task.id, state),
        )

    def _run_unknown_face_clustering(self, task: ProjectTask) -> dict:
        max_faces = int((task.request_params or {}).get("max_faces") or 500)
        self._persist_progress(
            task.id,
            build_queued_progress_payload(
                task.task_type,
                task.request_params,
                project_id=task.project_id,
            ),
        )
        result = cluster_unknown_faces(
            self._db,
            project_id=task.project_id,
            max_faces=max_faces,
            progress_callback=lambda state: self._persist_progress(
                task.id,
                self._with_task_id(state, task.id),
            ),
        )
        return build_face_cluster_result_payload(
            project_id=task.project_id,
            task_id=task.id,
            max_faces=max_faces,
            clusters_created=result.clusters_created,
            persons_created=result.persons_created,
            faces_clustered=result.faces_clustered,
            assignments_created=result.assignments_created,
        )

    def _run_face_scan_project(self, task: ProjectTask) -> dict:
        params = dict(task.request_params or {})
        service = FaceScanBatchService(self._db)
        plan = service.plan(
            task.project_id,
            scope=str(params.get("scope") or "missing"),
            photo_ids=[int(photo_id) for photo_id in params.get("photo_ids") or []],
            force=bool(params.get("force") or False),
        )
        enqueue_result = service.enqueue(plan)
        return build_face_scan_project_result_payload(
            project_id=task.project_id,
            task_id=task.id,
            request_params=params,
            created_jobs=enqueue_result.created_jobs,
            skipped_active_jobs=enqueue_result.skipped_active,
        )

    def _run_face_rematch_unknown(self, task: ProjectTask) -> dict:
        params = dict(task.request_params or {})
        max_faces = int(params.get("max_faces") or 1000)
        scope = str(params.get("scope") or "unknown")
        person_id = int(params["person_id"]) if params.get("person_id") is not None else None
        start_time = _parse_iso_datetime(params.get("start_time"))
        end_time = _parse_iso_datetime(params.get("end_time"))
        result = rematch_unknown_faces(
            self._db,
            project_id=task.project_id,
            max_faces=max_faces,
            scope=scope,
            person_id=person_id,
            start_time=start_time,
            end_time=end_time,
            progress_callback=lambda state: self._persist_progress(
                task.id,
                self._with_task_id(state, task.id),
            ),
        )
        return build_face_rematch_result_payload(
            project_id=task.project_id,
            task_id=task.id,
            max_faces=max_faces,
            scope=scope,
            person_id=person_id,
            start_time=start_time.isoformat() if start_time else None,
            end_time=end_time.isoformat() if end_time else None,
            faces_considered=result.faces_considered,
            matched_faces=result.matched_faces,
            auto_assigned=result.auto_assigned,
            review_pending=result.review_pending,
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

    @staticmethod
    def _with_task_id(state: dict, task_id: int) -> dict:
        payload = dict(state)
        payload["task_id"] = task_id
        return payload



def _parse_iso_datetime(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None
