from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.project_task import ProjectTask
from ..models.project import Project
from ..schemas.face import FaceClusterUnknownStatusResponse
from ..schemas.scan import ScanStatus

TASK_TYPE_LIBRARY_SCAN = "library_scan"
TASK_TYPE_LIBRARY_REINDEX = "library_reindex"
TASK_TYPE_UNKNOWN_FACE_CLUSTERING = "unknown_face_clustering"
TASK_TYPE_FACE_SCAN_PROJECT = "face_scan_project"

SCAN_TASK_TYPES: tuple[str, ...] = (
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_LIBRARY_REINDEX,
)
FACE_CLUSTER_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_UNKNOWN_FACE_CLUSTERING,)
FACE_SCAN_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_FACE_SCAN_PROJECT,)


@dataclass(frozen=True)
class EnqueueProjectTaskResult:
    task: ProjectTask
    created: bool


def empty_scan_state() -> dict:
    return {
        "running": False,
        "scanned": 0,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "current_path": None,
        "message": "idle",
        "recent_errors": [],
        "recent_files": [],
    }


def empty_face_cluster_state(
    *,
    project_id: int = 0,
    max_faces: int = 500,
) -> dict:
    return {
        "project_id": project_id,
        "task_id": None,
        "status": "idle",
        "running": False,
        "max_faces": max_faces,
        "clusters_created": 0,
        "persons_created": 0,
        "faces_clustered": 0,
        "assignments_created": 0,
        "errors": 0,
        "recent_errors": [],
        "message": "idle",
    }


def get_active_scan_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_active_project_task(db, project_id, SCAN_TASK_TYPES)


def get_latest_scan_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_latest_project_task(db, project_id, SCAN_TASK_TYPES)


def get_active_face_cluster_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_active_project_task(db, project_id, FACE_CLUSTER_TASK_TYPES)


def get_latest_face_cluster_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_latest_project_task(db, project_id, FACE_CLUSTER_TASK_TYPES)


def get_active_face_scan_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_active_project_task(db, project_id, FACE_SCAN_TASK_TYPES)


def get_latest_face_scan_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_latest_project_task(db, project_id, FACE_SCAN_TASK_TYPES)


def _get_active_project_task(
    db: Session,
    project_id: int,
    task_types: tuple[str, ...],
) -> Optional[ProjectTask]:
    return (
        db.query(ProjectTask)
        .filter(
            ProjectTask.project_id == project_id,
            ProjectTask.task_type.in_(task_types),
            ProjectTask.status.in_(["queued", "running"]),
        )
        .order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc())
        .first()
    )


def _get_latest_project_task(
    db: Session,
    project_id: int,
    task_types: tuple[str, ...],
) -> Optional[ProjectTask]:
    return (
        db.query(ProjectTask)
        .filter(
            ProjectTask.project_id == project_id,
            ProjectTask.task_type.in_(task_types),
        )
        .order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc())
        .first()
    )


def enqueue_scan_task(
    db: Session,
    *,
    project_id: int,
    task_type: str,
    request_params: Optional[dict] = None,
) -> EnqueueProjectTaskResult:
    return enqueue_unique_project_task(
        db,
        project_id=project_id,
        task_type=task_type,
        active_task_types=SCAN_TASK_TYPES,
        request_params=request_params,
    )


def enqueue_face_cluster_task(
    db: Session,
    *,
    project_id: int,
    max_faces: int,
) -> EnqueueProjectTaskResult:
    return enqueue_unique_project_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
        active_task_types=FACE_CLUSTER_TASK_TYPES,
        request_params={"max_faces": max_faces},
    )


def enqueue_face_scan_project_task(
    db: Session,
    *,
    project_id: int,
    request_params: Optional[dict] = None,
) -> EnqueueProjectTaskResult:
    return enqueue_unique_project_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_FACE_SCAN_PROJECT,
        active_task_types=FACE_SCAN_TASK_TYPES,
        request_params=request_params,
    )


def enqueue_unique_project_task(
    db: Session,
    *,
    project_id: int,
    task_type: str,
    active_task_types: tuple[str, ...],
    request_params: Optional[dict] = None,
) -> EnqueueProjectTaskResult:
    # Serialize enqueue decisions per project where the database supports row locks.
    db.query(Project.id).filter(Project.id == project_id).with_for_update().first()
    active_task = _get_active_project_task(db, project_id, active_task_types)
    if active_task is not None:
        return EnqueueProjectTaskResult(task=active_task, created=False)

    task = ProjectTask(
        project_id=project_id,
        task_type=task_type,
        status="queued",
        retry_count=0,
        request_params=request_params,
        progress_payload=build_queued_progress_payload(task_type, request_params, project_id=project_id),
        result_payload=None,
        error_message=None,
        updated_at=_now_utc(),
    )
    db.add(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active_task = _get_active_project_task(db, project_id, active_task_types)
        if active_task is not None:
            return EnqueueProjectTaskResult(task=active_task, created=False)
        raise
    db.refresh(task)
    return EnqueueProjectTaskResult(task=task, created=True)


def enqueue_project_task(
    db: Session,
    *,
    project_id: int,
    task_type: str,
    request_params: Optional[dict] = None,
) -> ProjectTask:
    task = ProjectTask(
        project_id=project_id,
        task_type=task_type,
        status="queued",
        retry_count=0,
        request_params=request_params,
        progress_payload=build_queued_progress_payload(task_type, request_params, project_id=project_id),
        result_payload=None,
        error_message=None,
        updated_at=_now_utc(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def build_scan_status(task: Optional[ProjectTask]) -> ScanStatus:
    if task is None:
        return ScanStatus(**empty_scan_state())

    payload = dict(empty_scan_state())
    payload.update(task.progress_payload or {})

    if task.status in ("queued", "running"):
        payload["running"] = True
        payload["message"] = payload.get("message") or _default_running_message(
            task.task_type,
            task.request_params,
        )
        return ScanStatus(**payload)

    payload["running"] = False
    if task.status == "success":
        payload["message"] = payload.get("message") or "done"
        return ScanStatus(**payload)
    if task.status == "completed_with_errors":
        payload["errors"] = max(int(payload.get("errors") or 0), 1)
        payload["message"] = payload.get("message") or "done_with_errors"
        return ScanStatus(**payload)

    error_text = (task.error_message or "").strip()
    recent_errors = list(payload.get("recent_errors") or [])
    if error_text and error_text not in recent_errors:
        recent_errors.append(error_text)
    payload["recent_errors"] = recent_errors
    payload["errors"] = max(int(payload.get("errors") or 0), 1)
    payload["message"] = error_text or payload.get("message") or "done_with_errors"
    return ScanStatus(**payload)


def build_face_cluster_status(task: Optional[ProjectTask]) -> FaceClusterUnknownStatusResponse:
    if task is None:
        return FaceClusterUnknownStatusResponse(**empty_face_cluster_state())

    request_params = dict(task.request_params or {})
    max_faces = int(request_params.get("max_faces") or 500)
    payload = empty_face_cluster_state(project_id=task.project_id, max_faces=max_faces)

    if task.status == "success":
        payload.update(task.result_payload or {})
    else:
        payload.update(task.progress_payload or {})

    payload["project_id"] = task.project_id
    payload["task_id"] = task.id
    payload["status"] = task.status
    payload["running"] = task.status in ("queued", "running")
    payload["max_faces"] = int(payload.get("max_faces") or max_faces)

    if task.status == "failed":
        error_text = (task.error_message or "").strip()
        recent_errors = list(payload.get("recent_errors") or [])
        if error_text and error_text not in recent_errors:
            recent_errors.append(error_text)
        payload["recent_errors"] = recent_errors
        payload["errors"] = max(int(payload.get("errors") or 0), 1)
        payload["message"] = error_text or payload.get("message") or "clustering_failed"
    elif not payload.get("message"):
        payload["message"] = _default_running_message(task.task_type, request_params)

    return FaceClusterUnknownStatusResponse(**payload)


def build_queued_progress_payload(
    task_type: str,
    request_params: Optional[dict],
    *,
    project_id: int,
) -> dict:
    payload = empty_project_task_state(
        task_type,
        request_params,
        project_id=project_id,
    )
    payload["running"] = True
    payload["message"] = _default_running_message(task_type, request_params)
    return payload


def empty_project_task_state(
    task_type: str,
    request_params: Optional[dict] = None,
    *,
    project_id: int = 0,
) -> dict:
    if task_type == TASK_TYPE_UNKNOWN_FACE_CLUSTERING:
        max_faces = int((request_params or {}).get("max_faces") or 500)
        return empty_face_cluster_state(project_id=project_id, max_faces=max_faces)
    if task_type == TASK_TYPE_FACE_SCAN_PROJECT:
        params = request_params or {}
        return {
            "project_id": project_id,
            "task_id": None,
            "status": "idle",
            "running": False,
            "scope": params.get("scope") or "missing",
            "total_photos": int(params.get("total_photos") or 0),
            "candidate_count": int(params.get("candidate_count") or 0),
            "created_jobs": 0,
            "skipped_active_jobs": int(params.get("skipped_active_jobs") or 0),
            "skipped_already_scanned": int(params.get("skipped_already_scanned") or 0),
            "skipped_other_project": int(params.get("skipped_other_project") or 0),
            "stale_count": int(params.get("stale_count") or 0),
            "failed_count": int(params.get("failed_count") or 0),
            "errors": 0,
            "recent_errors": [],
            "message": "idle",
        }
    return empty_scan_state()


def _default_running_message(task_type: str, request_params: Optional[dict]) -> str:
    if task_type == TASK_TYPE_LIBRARY_REINDEX:
        scope = (request_params or {}).get("scope") or "missing_metadata"
        return f"reindexing ({scope})"
    if task_type == TASK_TYPE_UNKNOWN_FACE_CLUSTERING:
        max_faces = int((request_params or {}).get("max_faces") or 500)
        return f"clustering unknown faces (max_faces={max_faces})"
    if task_type == TASK_TYPE_FACE_SCAN_PROJECT:
        scope = (request_params or {}).get("scope") or "missing"
        return f"queuing face scan jobs ({scope})"
    return "scanning"


def build_face_scan_project_result_payload(
    *,
    project_id: int,
    task_id: int,
    request_params: Optional[dict],
    created_jobs: int,
    skipped_active_jobs: int,
) -> dict:
    payload = empty_project_task_state(
        TASK_TYPE_FACE_SCAN_PROJECT,
        request_params,
        project_id=project_id,
    )
    payload.update(
        task_id=task_id,
        status="success",
        running=False,
        created_jobs=created_jobs,
        skipped_active_jobs=skipped_active_jobs,
        message="Project face scan jobs queued",
    )
    return payload


def build_face_cluster_result_payload(
    *,
    project_id: int,
    task_id: int,
    max_faces: int,
    clusters_created: int,
    persons_created: int,
    faces_clustered: int,
    assignments_created: int,
) -> dict:
    payload = empty_face_cluster_state(project_id=project_id, max_faces=max_faces)
    payload.update(
        task_id=task_id,
        status="success",
        running=False,
        clusters_created=clusters_created,
        persons_created=persons_created,
        faces_clustered=faces_clustered,
        assignments_created=assignments_created,
        message="Unknown face clustering completed",
    )
    return payload


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)
