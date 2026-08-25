from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..api.deps import get_current_user, require_project, require_project_manager
from ..database import get_db
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.photo_quarantine import (
    PhotoQuarantineBatchItemResponse,
    PhotoQuarantineBatchRequest,
    PhotoQuarantineBatchResponse,
    PhotoQuarantineCalibrationResponse,
    PhotoQuarantineItemResponse,
    PhotoQuarantineLabelRequest,
    PhotoQuarantineListResponse,
    PhotoQuarantineReconciliationResponse,
    ProjectPhotoQuarantineSettingsResponse,
    ProjectPhotoQuarantineSettingsUpdate,
)
from ..schemas.user import CurrentUser
from ..services.photo_quarantine_service import (
    PhotoQuarantineConflict,
    PhotoQuarantineError,
    PhotoQuarantineService,
)
from ..services.project_task_service import enqueue_photo_quarantine_task
from ..schemas.project_task import ProjectTaskResponse
from ..services.project_tasks_app_service import ProjectTasksAppService

router = APIRouter(prefix="/projects", tags=["photo-quarantine"])


@router.post(
    "/{project_id}/photo-quarantine/batches",
    response_model=PhotoQuarantineBatchResponse,
)
def run_photo_quarantine_batch(
    body: PhotoQuarantineBatchRequest,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = PhotoQuarantineService(db).batch_action(
        project_id=project.id,
        item_ids=body.item_ids,
        action=body.action,
        labeled_by=current_user.username,
    )
    return PhotoQuarantineBatchResponse(
        requested=len(result.results),
        succeeded=result.succeeded,
        failed=result.failed,
        results=[
            PhotoQuarantineBatchItemResponse(
                item_id=item.item_id,
                succeeded=item.succeeded,
                item=(
                    PhotoQuarantineItemResponse.model_validate(item.item)
                    if item.item is not None
                    else None
                ),
                error_code=item.error_code,
                message=item.message,
            )
            for item in result.results
        ],
    )


@router.post(
    "/{project_id}/photo-quarantine/runs",
    response_model=ProjectTaskResponse,
)
def start_photo_quarantine_run(
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    result = enqueue_photo_quarantine_task(
        db,
        project_id=project.id,
        trigger="manual",
        ignore_window=True,
    )
    return ProjectTasksAppService(db).get_task(
        project_id=project.id,
        task_id=result.task.id,
    )


@router.get(
    "/{project_id}/photo-quarantine/settings",
    response_model=ProjectPhotoQuarantineSettingsResponse,
)
def get_photo_quarantine_settings(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return PhotoQuarantineService(db).get_or_create_settings(project.id)


@router.put(
    "/{project_id}/photo-quarantine/settings",
    response_model=ProjectPhotoQuarantineSettingsResponse,
)
def update_photo_quarantine_settings(
    body: ProjectPhotoQuarantineSettingsUpdate,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    return PhotoQuarantineService(db).update_settings(
        project.id, body.model_dump()
    )


@router.get(
    "/{project_id}/photo-quarantine/items",
    response_model=PhotoQuarantineListResponse,
)
def list_photo_quarantine_items(
    status: Optional[str] = None,
    human_label: Optional[Literal["KEEP", "TRASH", "UNLABELED"]] = None,
    classification: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    total, items = PhotoQuarantineService(db).list_items(
        project_id=project.id,
        status=status,
        human_label=human_label,
        classification=classification,
        limit=limit,
        offset=offset,
    )
    return PhotoQuarantineListResponse(total=total, items=items)


@router.post(
    "/{project_id}/photo-quarantine/reconciliations",
    response_model=PhotoQuarantineReconciliationResponse,
)
def reconcile_photo_quarantine_items(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    result = PhotoQuarantineService(db).reconcile_deleted(project_id=project.id)
    return PhotoQuarantineReconciliationResponse(
        checked=result.checked,
        confirmed=result.confirmed,
        remaining=result.remaining,
        failed=result.failed,
    )


@router.post(
    "/{project_id}/photo-quarantine/items/{item_id}/request-delete",
    response_model=PhotoQuarantineItemResponse,
)
def request_delete_photo_quarantine_item(
    item_id: int,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).request_delete(
            project_id=project.id, item_id=item_id, labeled_by=current_user.username
        ).item
    except PhotoQuarantineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{project_id}/photo-quarantine/items/{item_id}/move",
    response_model=PhotoQuarantineItemResponse,
)
def move_photo_quarantine_item(
    item_id: int,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).request_delete(
            project_id=project.id, item_id=item_id, labeled_by=current_user.username
        ).item
    except PhotoQuarantineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{project_id}/photo-quarantine/items/{item_id}/restore",
    response_model=PhotoQuarantineItemResponse,
)
def restore_photo_quarantine_item(
    item_id: int,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).restore(
            project_id=project.id, item_id=item_id, labeled_by=current_user.username
        )
    except PhotoQuarantineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{project_id}/photo-quarantine/items/{item_id}/confirm-deleted",
    response_model=PhotoQuarantineItemResponse,
)
def confirm_photo_quarantine_item_deleted(
    item_id: int,
    project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).confirm_deleted(
            project_id=project.id, item_id=item_id
        )
    except PhotoQuarantineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{project_id}/photo-quarantine/items/{item_id}/keep",
    response_model=PhotoQuarantineItemResponse,
)
def keep_photo_quarantine_item(
    item_id: int,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).keep(
            project_id=project.id, item_id=item_id, labeled_by=current_user.username
        )
    except PhotoQuarantineConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put(
    "/{project_id}/photo-quarantine/items/{item_id}/label",
    response_model=PhotoQuarantineItemResponse,
)
def label_photo_quarantine_item(
    item_id: int,
    body: PhotoQuarantineLabelRequest,
    project: Project = Depends(require_project_manager),
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return PhotoQuarantineService(db).label(
            project_id=project.id,
            item_id=item_id,
            label=body.label,
            note=body.note,
            labeled_by=current_user.username,
        )
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{project_id}/photo-quarantine/calibration",
    response_model=PhotoQuarantineCalibrationResponse,
)
def get_photo_quarantine_calibration(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    return PhotoQuarantineService(db).calibration_report(project_id=project.id)


@router.get("/{project_id}/photo-quarantine/calibration.csv")
def export_photo_quarantine_calibration(
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "item_id",
            "photo_id",
            "classification",
            "model_decision",
            "confidence",
            "human_label",
            "human_label_note",
            "human_labeled_by",
            "human_labeled_at",
            "model_name",
            "prompt_version",
        ]
    )
    for item in PhotoQuarantineService(db).list_labeled_items(project_id=project.id):
        writer.writerow(
            [
                item.id,
                item.photo_id,
                item.classification,
                item.first_result.get("decision"),
                item.confidence,
                item.human_label,
                item.human_label_note,
                item.human_labeled_by,
                item.human_labeled_at.isoformat() if item.human_labeled_at else None,
                item.model_name,
                item.prompt_version,
            ]
        )
    response = StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8"
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="photo-quarantine-calibration-project-{project.id}.csv"'
    )
    return response


@router.get("/{project_id}/photo-quarantine/items/{item_id}/thumbnail")
def get_photo_quarantine_thumbnail(
    item_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    service = PhotoQuarantineService(db)
    try:
        item = service.get_item(project_id=project.id, item_id=item_id)
    except PhotoQuarantineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    photo = (
        db.query(Photo)
        .filter(Photo.id == item.photo_id, Photo.project_id == project.id)
        .first()
    )
    if photo is None or not photo.thumbnail_path or not project.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    thumbnail_root = Path(project.thumbnail_path).expanduser().resolve()
    thumbnail_path = Path(photo.thumbnail_path).expanduser().resolve()
    try:
        thumbnail_path.relative_to(thumbnail_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Thumbnail path is outside project storage") from exc
    if not thumbnail_path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return FileResponse(thumbnail_path)
