from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.project_task import ProjectTask
from ..models.project import Project
from ..schemas.face import FaceClusterUnknownStatusResponse, FaceRematchUnknownStatusResponse
from ..schemas.scan import ScanStatus

TASK_TYPE_LIBRARY_SCAN = "library_scan"
TASK_TYPE_LIBRARY_REINDEX = "library_reindex"
TASK_TYPE_UNKNOWN_FACE_CLUSTERING = "unknown_face_clustering"
TASK_TYPE_FACE_SCAN_PROJECT = "face_scan_project"
TASK_TYPE_FACE_REMATCH_UNKNOWN = "face_rematch_unknown"
TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS = "photo_quarantine_analysis"

SCAN_TASK_TYPES: tuple[str, ...] = (
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_LIBRARY_REINDEX,
)
FACE_CLUSTER_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_UNKNOWN_FACE_CLUSTERING,)
FACE_SCAN_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_FACE_SCAN_PROJECT,)
FACE_REMATCH_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_FACE_REMATCH_UNKNOWN,)
PHOTO_QUARANTINE_TASK_TYPES: tuple[str, ...] = (TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS,)
ACTIVE_TASK_STATUSES: tuple[str, ...] = ("queued", "running", "paused")


@dataclass(frozen=True)
class EnqueueProjectTaskResult:
    task: ProjectTask
    created: bool


def empty_scan_state() -> dict:
    return {
        "task_id": None,
        "running": False,
        "scanned": 0,
        "discovered_count": 0,
        "prepared_count": 0,
        "persisted_count": 0,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "current_stage": None,
        "current_path": None,
        "queue_depth": 0,
        "last_stage_latency_ms": None,
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


def get_active_face_rematch_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_active_project_task(db, project_id, FACE_REMATCH_TASK_TYPES)


def get_latest_face_rematch_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_latest_project_task(db, project_id, FACE_REMATCH_TASK_TYPES)


def get_active_photo_quarantine_task(db: Session, project_id: int) -> Optional[ProjectTask]:
    return _get_active_project_task(db, project_id, PHOTO_QUARANTINE_TASK_TYPES)


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
            ProjectTask.status.in_(ACTIVE_TASK_STATUSES),
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


def enqueue_face_rematch_unknown_task(
    db: Session,
    *,
    project_id: int,
    max_faces: int,
    scope: str = "unknown",
    person_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    trigger: Optional[str] = None,
    schedule: Optional[str] = None,
) -> EnqueueProjectTaskResult:
    request_params: dict[str, object] = {"max_faces": max_faces, "scope": scope}
    if person_id is not None:
        request_params["person_id"] = int(person_id)
    if start_time:
        request_params["start_time"] = start_time
    if end_time:
        request_params["end_time"] = end_time
    if trigger:
        request_params["trigger"] = trigger
    if schedule:
        request_params["schedule"] = schedule
    return enqueue_unique_project_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_FACE_REMATCH_UNKNOWN,
        active_task_types=FACE_REMATCH_TASK_TYPES,
        request_params=request_params,
    )


def enqueue_photo_quarantine_task(
    db: Session,
    *,
    project_id: int,
    trigger: str = "schedule",
    ignore_window: bool = False,
) -> EnqueueProjectTaskResult:
    return enqueue_unique_project_task(
        db,
        project_id=project_id,
        task_type=TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS,
        active_task_types=PHOTO_QUARANTINE_TASK_TYPES,
        request_params={"trigger": trigger, "ignore_window": ignore_window},
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


def request_project_task_cancel(
    db: Session,
    *,
    project_id: int,
    task_types: tuple[str, ...],
) -> Optional[ProjectTask]:
    task = _get_active_project_task(db, project_id, task_types)
    if task is None:
        return None

    return _request_task_cancel(db, task)


def request_project_task_cancel_by_id(
    db: Session,
    *,
    project_id: int,
    task_id: int,
) -> Optional[ProjectTask]:
    task = get_project_task(db, project_id=project_id, task_id=task_id)
    if task is None or task.status not in ACTIVE_TASK_STATUSES:
        return task

    return _request_task_cancel(db, task)


def _request_task_cancel(db: Session, task: ProjectTask) -> ProjectTask:
    now = _now_utc()
    progress = dict(
        task.progress_payload
        or empty_project_task_state(
            task.task_type,
            task.request_params,
            project_id=task.project_id,
        )
    )
    progress["cancel_requested"] = True
    progress.pop("pause_requested", None)
    progress["message"] = "cancelling"

    if task.status in ("queued", "paused"):
        task.status = "cancelled"
        task.finished_at = now
        progress["running"] = False
        progress["message"] = "cancelled"
        task.result_payload = dict(progress)
        task.error_message = None
    else:
        progress["running"] = True

    task.progress_payload = progress
    task.updated_at = now
    db.commit()
    db.refresh(task)
    return task


def request_project_task_pause(
    db: Session,
    *,
    project_id: int,
    task_id: int,
) -> Optional[ProjectTask]:
    task = get_project_task(db, project_id=project_id, task_id=task_id)
    if task is None or task.status not in ("queued", "running"):
        return task

    now = _now_utc()
    progress = dict(
        task.progress_payload
        or empty_project_task_state(
            task.task_type,
            task.request_params,
            project_id=task.project_id,
        )
    )
    progress["pause_requested"] = True
    progress["message"] = "pausing"

    if task.status == "queued":
        task.status = "paused"
        progress["running"] = False
        progress["message"] = "paused"
    else:
        progress["running"] = True

    task.progress_payload = progress
    task.updated_at = now
    db.commit()
    db.refresh(task)
    return task


def resume_project_task(
    db: Session,
    *,
    project_id: int,
    task_id: int,
) -> Optional[ProjectTask]:
    task = get_project_task(db, project_id=project_id, task_id=task_id)
    if task is None or task.status != "paused":
        return task

    progress = dict(
        task.progress_payload
        or empty_project_task_state(
            task.task_type,
            task.request_params,
            project_id=task.project_id,
        )
    )
    progress.pop("pause_requested", None)
    progress["running"] = True
    progress["message"] = _default_running_message(task.task_type, task.request_params)
    task.status = "queued"
    task.finished_at = None
    task.progress_payload = progress
    task.updated_at = _now_utc()
    db.commit()
    db.refresh(task)
    return task


def list_project_tasks(
    db: Session,
    *,
    project_id: int,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[ProjectTask]]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    query = db.query(ProjectTask).filter(ProjectTask.project_id == project_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if statuses:
            query = query.filter(ProjectTask.status.in_(statuses))
    if task_type:
        task_types = [item.strip() for item in task_type.split(",") if item.strip()]
        if task_types:
            query = query.filter(ProjectTask.task_type.in_(task_types))

    total = query.count()
    items = (
        query.order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return total, items


def list_project_task_failures(
    db: Session,
    *,
    project_id: int,
    task_id: int,
    limit: int = 50,
    offset: int = 0,
) -> Optional[tuple[int, list[dict[str, Any]]]]:
    task = get_project_task(db, project_id=project_id, task_id=task_id)
    if task is None:
        return None

    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    items = extract_task_failures(task)
    return len(items), items[offset : offset + limit]


def get_project_task(db: Session, *, project_id: int, task_id: int) -> Optional[ProjectTask]:
    return (
        db.query(ProjectTask)
        .filter(ProjectTask.project_id == project_id, ProjectTask.id == task_id)
        .first()
    )


def extract_task_failures(task: ProjectTask) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    error_text = (task.error_message or "").strip()
    if error_text:
        _append_failure(
            failures,
            seen,
            {
                "key": f"task_error:{task.id}:{len(failures)}",
                "source": "task_error",
                "message": error_text,
                "path": None,
                "status": "failed",
                "timestamp": task.finished_at or task.updated_at,
                "details": {"task_status": task.status},
            },
        )

    for payload_name, payload in (("result_payload", task.result_payload), ("progress_payload", task.progress_payload)):
        if not isinstance(payload, dict):
            continue

        for entry in reversed(list(payload.get("recent_files") or [])):
            normalized = _normalize_recent_file_failure(entry, payload_name=payload_name)
            if normalized is None:
                continue
            _append_failure(failures, seen, normalized)

        for message in reversed(list(payload.get("recent_errors") or [])):
            normalized = _normalize_recent_error_failure(message, payload_name=payload_name)
            if normalized is None:
                continue
            _append_failure(failures, seen, normalized)
    return failures


def extract_task_recent_errors(task: ProjectTask) -> list[str]:
    errors: list[str] = []
    failures = extract_task_failures(task)
    failures.sort(key=lambda failure: 1 if failure.get("source") == "task_error" else 0)
    for failure in failures:
        message = str(failure.get("message") or "").strip()
        if message and message not in errors:
            errors.append(message)
    return errors


def _append_failure(
    failures: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
    failure: dict[str, Any],
) -> None:
    dedupe_key = (
        failure.get("source"),
        failure.get("message"),
        failure.get("path"),
        failure.get("status"),
        failure.get("timestamp"),
    )
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    failures.append(failure)


def _normalize_recent_file_failure(
    entry: Any,
    *,
    payload_name: str,
) -> Optional[dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    status = str(entry.get("status") or "").strip().lower()
    message = str(entry.get("message") or "").strip()
    if status not in {"failed", "error"} and not message:
        return None

    path = entry.get("path")
    timestamp = _coerce_failure_timestamp(entry.get("timestamp"))
    details = {
        key: value
        for key, value in entry.items()
        if key not in {"path", "status", "message", "timestamp"}
    }
    if payload_name:
        details["payload"] = payload_name
    return {
        "key": f"file_progress:{payload_name}:{path or 'unknown'}:{timestamp or 'na'}:{message or status}",
        "source": "file_progress",
        "message": message or status or "task failure",
        "path": str(path) if path else None,
        "status": status or None,
        "timestamp": timestamp,
        "details": details or None,
    }


def _normalize_recent_error_failure(
    entry: Any,
    *,
    payload_name: str,
) -> Optional[dict[str, Any]]:
    message = str(entry or "").strip()
    if not message:
        return None
    return {
        "key": f"recent_error:{payload_name}:{message}",
        "source": "recent_error",
        "message": message,
        "path": None,
        "status": "failed",
        "timestamp": None,
        "details": {"payload": payload_name},
    }


def _coerce_failure_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def build_scan_status(task: Optional[ProjectTask]) -> ScanStatus:
    if task is None:
        return ScanStatus(**empty_scan_state())

    payload = dict(empty_scan_state())
    payload.update(task.progress_payload or {})
    payload["task_id"] = task.id

    if task.status in ("queued", "running"):
        payload["running"] = True
        payload["message"] = payload.get("message") or _default_running_message(
            task.task_type,
            task.request_params,
        )
        return ScanStatus(**payload)

    payload["running"] = False
    if task.status == "paused":
        payload["message"] = "paused"
        return ScanStatus(**payload)
    if task.status == "success":
        payload["message"] = payload.get("message") or "done"
        return ScanStatus(**payload)
    if task.status == "completed_with_errors":
        payload["errors"] = max(int(payload.get("errors") or 0), 1)
        payload["message"] = payload.get("message") or "done_with_errors"
        return ScanStatus(**payload)
    if task.status == "cancelled":
        payload["message"] = "cancelled"
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


def build_face_rematch_status(task: Optional[ProjectTask]) -> FaceRematchUnknownStatusResponse:
    if task is None:
        return FaceRematchUnknownStatusResponse(**empty_face_rematch_state())

    request_params = dict(task.request_params or {})
    max_faces = int(request_params.get("max_faces") or 1000)
    payload = empty_face_rematch_state(
        project_id=task.project_id,
        max_faces=max_faces,
        scope=str(request_params.get("scope") or "unknown"),
        person_id=(
            int(request_params["person_id"])
            if request_params.get("person_id") is not None
            else None
        ),
        start_time=(str(request_params.get("start_time")) if request_params.get("start_time") else None),
        end_time=(str(request_params.get("end_time")) if request_params.get("end_time") else None),
    )

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
        payload["message"] = error_text or payload.get("message") or "rematch_failed"
    elif not payload.get("message"):
        payload["message"] = _default_running_message(task.task_type, request_params)

    return FaceRematchUnknownStatusResponse(**payload)


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
    if task_type == TASK_TYPE_FACE_REMATCH_UNKNOWN:
        params = request_params or {}
        max_faces = int(params.get("max_faces") or 1000)
        return empty_face_rematch_state(
            project_id=project_id,
            max_faces=max_faces,
            scope=str(params.get("scope") or "unknown"),
            person_id=(int(params["person_id"]) if params.get("person_id") is not None else None),
            start_time=(str(params.get("start_time")) if params.get("start_time") else None),
            end_time=(str(params.get("end_time")) if params.get("end_time") else None),
        )
    if task_type == TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS:
        return {
            "project_id": project_id,
            "task_id": None,
            "running": False,
            "analyzed": 0,
            "kept": 0,
            "review": 0,
            "quarantined": 0,
            "errors": 0,
            "window_closed": False,
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
    if task_type == TASK_TYPE_FACE_REMATCH_UNKNOWN:
        max_faces = int((request_params or {}).get("max_faces") or 1000)
        scope = str((request_params or {}).get("scope") or "unknown")
        return f"rematching faces (scope={scope}, max_faces={max_faces})"
    if task_type == TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS:
        return "analyzing photo quarantine candidates"
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


def empty_face_rematch_state(
    *,
    project_id: int = 0,
    max_faces: int = 1000,
    scope: str = "unknown",
    person_id: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> dict:
    return {
        "project_id": project_id,
        "task_id": None,
        "status": "idle",
        "running": False,
        "max_faces": max_faces,
        "scope": scope,
        "person_id": person_id,
        "start_time": start_time,
        "end_time": end_time,
        "faces_considered": 0,
        "matched_faces": 0,
        "auto_assigned": 0,
        "review_pending": 0,
        "skipped_reason": None,
        "errors": 0,
        "recent_errors": [],
        "message": "idle",
    }


def build_face_rematch_result_payload(
    *,
    project_id: int,
    task_id: int,
    max_faces: int,
    scope: str,
    person_id: Optional[int],
    start_time: Optional[str],
    end_time: Optional[str],
    faces_considered: int,
    matched_faces: int,
    auto_assigned: int,
    review_pending: int,
    skipped_reason: Optional[str] = None,
) -> dict:
    payload = empty_face_rematch_state(
        project_id=project_id,
        max_faces=max_faces,
        scope=scope,
        person_id=person_id,
        start_time=start_time,
        end_time=end_time,
    )
    message = "Unknown face rematch completed"
    if skipped_reason == "no_eligible_embedded_faces":
        message = "No eligible embedded faces found. Run face scan first or adjust rematch scope."
    elif skipped_reason == "missing_people_tables":
        message = "People recognition tables are missing."

    payload.update(
        task_id=task_id,
        status="success",
        running=False,
        faces_considered=faces_considered,
        matched_faces=matched_faces,
        auto_assigned=auto_assigned,
        review_pending=review_pending,
        skipped_reason=skipped_reason,
        message=message,
    )
    return payload


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)
