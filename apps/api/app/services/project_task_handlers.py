from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from sqlalchemy.orm import Session

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
)
from .scanner import reindex_project, scan_project
from .unknown_face_clustering_service import cluster_unknown_faces


@dataclass(frozen=True)
class ProjectTaskRunContext:
    db: Session
    persist_progress: Callable[[int, dict], None]

    @staticmethod
    def with_task_id(state: dict, task_id: int) -> dict:
        payload = dict(state)
        payload["task_id"] = task_id
        return payload


class ProjectTaskHandler(Protocol):
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        ...


class LibraryScanTaskHandler:
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        return scan_project(
            context.db,
            task.project_id,
            progress_callback=lambda state: context.persist_progress(task.id, state),
        )


class LibraryReindexTaskHandler:
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        scope = str((task.request_params or {}).get("scope") or "missing_metadata")
        return reindex_project(
            context.db,
            task.project_id,
            scope=scope,
            progress_callback=lambda state: context.persist_progress(task.id, state),
        )


class UnknownFaceClusteringTaskHandler:
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        max_faces = int((task.request_params or {}).get("max_faces") or 500)
        context.persist_progress(
            task.id,
            build_queued_progress_payload(
                task.task_type,
                task.request_params,
                project_id=task.project_id,
            ),
        )
        result = cluster_unknown_faces(
            context.db,
            project_id=task.project_id,
            max_faces=max_faces,
            progress_callback=lambda state: context.persist_progress(
                task.id,
                context.with_task_id(state, task.id),
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


class FaceScanProjectTaskHandler:
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        params = dict(task.request_params or {})
        service = FaceScanBatchService(context.db)
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


class FaceRematchUnknownTaskHandler:
    def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
        params = dict(task.request_params or {})
        max_faces = int(params.get("max_faces") or 1000)
        scope = str(params.get("scope") or "unknown")
        person_id = int(params["person_id"]) if params.get("person_id") is not None else None
        start_time = _parse_iso_datetime(params.get("start_time"))
        end_time = _parse_iso_datetime(params.get("end_time"))
        result = rematch_unknown_faces(
            context.db,
            project_id=task.project_id,
            max_faces=max_faces,
            scope=scope,
            person_id=person_id,
            start_time=start_time,
            end_time=end_time,
            progress_callback=lambda state: context.persist_progress(
                task.id,
                context.with_task_id(state, task.id),
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


def build_default_project_task_handlers() -> dict[str, ProjectTaskHandler]:
    return {
        TASK_TYPE_LIBRARY_SCAN: LibraryScanTaskHandler(),
        TASK_TYPE_LIBRARY_REINDEX: LibraryReindexTaskHandler(),
        TASK_TYPE_UNKNOWN_FACE_CLUSTERING: UnknownFaceClusteringTaskHandler(),
        TASK_TYPE_FACE_SCAN_PROJECT: FaceScanProjectTaskHandler(),
        TASK_TYPE_FACE_REMATCH_UNKNOWN: FaceRematchUnknownTaskHandler(),
    }


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
