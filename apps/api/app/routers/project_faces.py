from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
import sqlalchemy as sa
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project, require_project_photo
from ..models.ai import AIJob
from ..face.providers import FaceRecognitionProviderUnavailableError
from ..models.face import FaceDetection, FaceEmbedding
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.face import (
    FaceClusterUnknownRequest,
    FaceClusterUnknownResponse,
    FaceClusterUnknownStatusResponse,
    FaceDetectionDetailResponse,
    FaceDetectionListResponse,
    FaceDetectionResponse,
    FaceScanProjectStartRequest,
    FaceScanProjectStartResponse,
    FaceScanProjectStatusResponse,
    FaceScanResponse,
)
from ..services.face_scan_batch_service import FaceScanBatchService
from ..services.face_scan_service import FaceScanDisabledError, FaceScanService
from ..services.unknown_face_clustering_service import cluster_unknown_faces
from ..services.project_task_service import (
    build_face_cluster_status,
    enqueue_face_cluster_task,
    get_active_face_cluster_task,
    get_latest_face_cluster_task,
)
from ..services.project_face_settings_service import get_or_create_project_face_settings

router = APIRouter(prefix="/projects", tags=["project-faces"])


@router.post("/{project_id}/photos/{photo_id}/face-scan", response_model=FaceScanResponse)
def scan_project_photo_faces(
    project_id: int,
    photo: Photo = Depends(require_project_photo),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanResponse:
    started_at = datetime.now(timezone.utc)
    job = AIJob(
        photo_id=photo.id,
        project_id=project_id,
        job_type="face_scan",
        status="running",
        retry_count=0,
        started_at=started_at,
        updated_at=started_at,
    )
    db.add(job)
    db.commit()

    try:
        result = FaceScanService(db).scan_photo(project_id, photo.id)
        cluster_assignments_created = 0
        cluster_result = None
        if result.faces_detected > 0:
            cluster_result = cluster_unknown_faces(
                db,
                project_id=project_id,
                max_faces=max(result.faces_detected, 1),
                photo_ids=[photo.id],
            )
            assignments_created = getattr(cluster_result, "assignments_created", 0)
            if isinstance(assignments_created, int):
                cluster_assignments_created = max(assignments_created, 0)

        response_payload = asdict(result)
        total_review_pending = int(result.review_pending) + cluster_assignments_created
        response_payload["review_pending"] = total_review_pending

        if total_review_pending <= 0 and result.faces_detected > 0:
            skipped_reason = getattr(cluster_result, "skipped_reason", None)
            embedded_ready = int(result.embeddings_created) + int(result.embeddings_updated)
            if skipped_reason == "missing_people_tables":
                response_payload["message"] = (
                    "Face scan completed: review unavailable because required tables "
                    "persons/person_face_assignments are missing. Run alembic upgrade head."
                )
            elif int(result.auto_assigned) > 0:
                response_payload["message"] = (
                    f"Face scan completed: {int(result.auto_assigned)} faces were auto-assigned "
                    "to existing people, so no review_pending entries were created."
                )
            elif embedded_ready <= 0:
                response_payload["message"] = (
                    "Face scan completed: no usable face embeddings were generated "
                    "(common causes: face too small or thumbnail fallback)."
                )
            else:
                response_payload["message"] = (
                    "Face scan completed: no review_pending entries were created for this photo."
                )
        finished_at = datetime.now(timezone.utc)
        job.status = "success"
        job.error_message = None
        job.parse_error = None
        job.raw_model_output = json.dumps(response_payload, ensure_ascii=True)
        job.finished_at = finished_at
        job.updated_at = finished_at
        db.commit()
    except FaceScanDisabledError as exc:
        db.rollback()
        failed_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)[:4000]
        job.parse_error = str(exc)[:4000]
        job.finished_at = failed_at
        job.updated_at = failed_at
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FaceRecognitionProviderUnavailableError as exc:
        db.rollback()
        failed_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)[:4000]
        job.parse_error = str(exc)[:4000]
        job.finished_at = failed_at
        job.updated_at = failed_at
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        db.rollback()
        failed_at = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = str(exc)[:4000]
        job.parse_error = str(exc)[:4000]
        job.finished_at = failed_at
        job.updated_at = failed_at
        db.commit()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        failed_at = datetime.now(timezone.utc)
        error_message = f"{type(exc).__name__}: {exc}"
        job.status = "failed"
        job.error_message = error_message[:4000]
        job.parse_error = error_message[:4000]
        job.finished_at = failed_at
        job.updated_at = failed_at
        db.commit()
        raise
    return FaceScanResponse.model_validate(response_payload)


@router.post(
    "/{project_id}/face-scan-project/start",
    response_model=FaceScanProjectStartResponse,
)
def start_project_face_scan_jobs(
    project_id: int,
    body: Optional[FaceScanProjectStartRequest] = None,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanProjectStartResponse:
    settings = get_or_create_project_face_settings(db, project_id)
    if not settings.face_recognition_enabled:
        raise HTTPException(
            status_code=409,
            detail="Face recognition is disabled for this project. Enable it in face settings first.",
        )

    body = body or FaceScanProjectStartRequest()
    if body.scope == "selected" and not body.photo_ids:
        raise HTTPException(
            status_code=400,
            detail="photo_ids is required when scope is selected",
        )

    service = FaceScanBatchService(db)
    plan = service.plan(
        project_id,
        scope=body.scope,
        photo_ids=body.photo_ids,
        force=body.force,
    )

    created_jobs = 0
    skipped_active = plan.skipped_active
    message = "Face scan batch plan generated"
    if not body.dry_run and plan.candidate_photo_ids:
        enqueue_result = service.enqueue(plan)
        created_jobs = enqueue_result.created_jobs
        skipped_active = enqueue_result.skipped_active
        message = "Project face scan jobs created"
    elif not body.dry_run:
        message = "No face scan jobs created"

    return FaceScanProjectStartResponse(
        project_id=project_id,
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


@router.get(
    "/{project_id}/face-scan-project/status",
    response_model=FaceScanProjectStatusResponse,
)
def get_project_face_scan_job_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanProjectStatusResponse:
    counts = FaceScanBatchService(db).status(project_id)
    return FaceScanProjectStatusResponse(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        total=sum(counts.values()),
    )


@router.post(
    "/{project_id}/face-cluster-unknown",
    response_model=FaceClusterUnknownResponse,
)
def cluster_project_unknown_faces(
    project_id: int,
    body: FaceClusterUnknownRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceClusterUnknownResponse:
    result = enqueue_face_cluster_task(
        db,
        project_id=project_id,
        max_faces=body.max_faces,
    )
    return FaceClusterUnknownResponse(
        message=(
            "Unknown face clustering queued"
            if result.created
            else "Unknown face clustering already in progress"
        ),
        status=build_face_cluster_status(result.task),
    )


@router.get(
    "/{project_id}/face-cluster-unknown/status",
    response_model=FaceClusterUnknownStatusResponse,
)
def get_cluster_project_unknown_faces_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceClusterUnknownStatusResponse:
    active_task = get_active_face_cluster_task(db, project_id)
    if active_task is not None:
        return build_face_cluster_status(active_task)
    return build_face_cluster_status(get_latest_face_cluster_task(db, project_id))


@router.get("/{project_id}/faces", response_model=FaceDetectionListResponse)
def list_project_faces(
    project_id: int,
    page: int = 1,
    page_size: int = Query(50, ge=1, le=200),
    photo_id: Optional[int] = None,
    status: Optional[str] = None,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceDetectionListResponse:
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    query = db.query(FaceDetection).filter(FaceDetection.project_id == project_id)
    if photo_id is not None:
        query = query.filter(FaceDetection.photo_id == photo_id)
    if status is not None:
        query = query.filter(FaceDetection.status == status)

    total = query.count()
    items = (
        query.order_by(FaceDetection.detected_at.desc().nullslast(), FaceDetection.id.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return FaceDetectionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[FaceDetectionResponse.model_validate(item) for item in items],
    )


@router.get("/{project_id}/faces/{face_id}", response_model=FaceDetectionDetailResponse)
def get_project_face(
    project_id: int,
    face_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceDetectionDetailResponse:
    face = (
        db.query(FaceDetection)
        .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
        .first()
    )
    if face is None:
        raise HTTPException(status_code=404, detail="Face not found in project")

    embeddings = (
        db.query(FaceEmbedding)
        .filter(
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.face_detection_id == face_id,
        )
        .order_by(FaceEmbedding.created_at.desc(), FaceEmbedding.id.desc())
        .all()
    )
    payload = FaceDetectionDetailResponse.model_validate(face)
    payload.embeddings = embeddings
    return payload


@router.get("/{project_id}/faces/{face_id}/crop")
def get_project_face_crop(
    project_id: int,
    face_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    face = (
        db.query(FaceDetection)
        .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
        .first()
    )
    if face is None:
        raise HTTPException(status_code=404, detail="Face not found in project")
    if not face.face_crop_path:
        raise HTTPException(status_code=404, detail="Face crop not stored for this detection")
    crop_path = Path(face.face_crop_path)
    if not crop_path.exists():
        raise HTTPException(status_code=404, detail="Face crop file not found")
    return FileResponse(
        str(crop_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
