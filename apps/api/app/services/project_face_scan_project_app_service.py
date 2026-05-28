from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..schemas.face import (
    FaceScanProjectStartRequest,
    FaceScanProjectStartResponse,
    FaceScanProjectStatusResponse,
)
from .face_scan_batch_service import FaceScanBatchService
from .project_face_settings_service import get_or_create_project_face_settings
from .project_task_service import (
    FACE_SCAN_TASK_TYPES,
    enqueue_face_scan_project_task,
    get_active_face_scan_task,
    get_latest_face_scan_task,
    request_project_task_cancel,
)


class FaceScanProjectDisabledError(RuntimeError):
    pass


class FaceScanProjectValidationError(RuntimeError):
    pass


class FaceScanProjectTaskNotFoundError(RuntimeError):
    pass


@dataclass
class ProjectFaceScanProjectAppService:
    db: Session

    def start(self, *, project_id: int, body: FaceScanProjectStartRequest) -> FaceScanProjectStartResponse:
        settings = get_or_create_project_face_settings(self.db, project_id)
        if not settings.face_recognition_enabled:
            raise FaceScanProjectDisabledError(
                "Face recognition is disabled for this project. Enable it in face settings first."
            )

        if body.scope == "selected" and not body.photo_ids:
            raise FaceScanProjectValidationError("photo_ids is required when scope is selected")

        plan = FaceScanBatchService(self.db).plan(
            project_id,
            scope=body.scope,
            photo_ids=body.photo_ids,
            force=body.force,
        )

        task_id = None
        task_created = False
        task_status = None
        created_jobs = 0
        skipped_active = plan.skipped_active
        message = "Face scan batch plan generated"

        if not body.dry_run and plan.candidate_photo_ids:
            task_result = enqueue_face_scan_project_task(
                self.db,
                project_id=project_id,
                request_params={
                    "scope": plan.scope,
                    "photo_ids": plan.candidate_photo_ids,
                    "force": body.force,
                    "total_photos": plan.total_photos,
                    "candidate_count": plan.candidate_count,
                    "skipped_active_jobs": plan.skipped_active,
                    "skipped_already_scanned": plan.skipped_already_scanned,
                    "skipped_other_project": plan.skipped_other_project,
                    "stale_count": plan.stale_count,
                    "failed_count": plan.failed_count,
                },
            )
            task_id = task_result.task.id
            task_created = task_result.created
            task_status = task_result.task.status
            if not task_result.created:
                skipped_active += plan.candidate_count
            message = (
                "Project face scan task queued"
                if task_result.created
                else "Project face scan task already in progress"
            )
        elif not body.dry_run:
            message = "No face scan jobs created"

        return FaceScanProjectStartResponse(
            project_id=project_id,
            task_id=task_id,
            task_created=task_created,
            task_status=task_status,
            created_jobs=created_jobs,
            skipped_active_jobs=skipped_active,
            scope=plan.scope,
            total_photos=plan.total_photos,
            candidate_count=plan.candidate_count,
            skipped_already_scanned=plan.skipped_already_scanned,
            skipped_other_project=plan.skipped_other_project,
            stale_count=plan.stale_count,
            failed_count=plan.failed_count,
            dry_run=body.dry_run,
            message=message,
        )

    def status(self, *, project_id: int) -> FaceScanProjectStatusResponse:
        counts = FaceScanBatchService(self.db).status(project_id)
        latest_task = get_active_face_scan_task(self.db, project_id) or get_latest_face_scan_task(
            self.db,
            project_id,
        )
        task_status = latest_task.status if latest_task is not None else None
        if latest_task is not None and latest_task.status in ("queued", "running"):
            counts[latest_task.status] = counts.get(latest_task.status, 0) + 1
        return FaceScanProjectStatusResponse(
            queued=counts.get("queued", 0),
            running=counts.get("running", 0),
            success=counts.get("success", 0),
            failed=counts.get("failed", 0),
            total=sum(counts.values()),
            task_id=latest_task.id if latest_task is not None else None,
            task_status=task_status,
        )

    def cancel(self, *, project_id: int) -> FaceScanProjectStatusResponse:
        task = request_project_task_cancel(
            self.db,
            project_id=project_id,
            task_types=FACE_SCAN_TASK_TYPES,
        )
        if task is None:
            raise FaceScanProjectTaskNotFoundError("No active face scan project task")
        counts = FaceScanBatchService(self.db).status(project_id)
        return FaceScanProjectStatusResponse(
            queued=counts.get("queued", 0),
            running=counts.get("running", 0),
            success=counts.get("success", 0),
            failed=counts.get("failed", 0),
            total=sum(counts.values()),
            task_id=task.id,
            task_status=task.status,
        )