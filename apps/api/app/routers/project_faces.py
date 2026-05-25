from __future__ import annotations

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
from ..services.project_face_settings_service import get_or_create_project_face_settings
from ..services.unknown_face_clustering_service import cluster_unknown_faces

router = APIRouter(prefix="/projects", tags=["project-faces"])


@router.post("/{project_id}/photos/{photo_id}/face-scan", response_model=FaceScanResponse)
def scan_project_photo_faces(
    project_id: int,
    photo: Photo = Depends(require_project_photo),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanResponse:
    try:
        result = FaceScanService(db).scan_photo(project_id, photo.id)
    except FaceScanDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FaceRecognitionProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FaceScanResponse.model_validate(result)


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
    result = cluster_unknown_faces(db, project_id=project_id, max_faces=body.max_faces)
    db.commit()
    return FaceClusterUnknownResponse(
        project_id=project_id,
        clusters_created=result.clusters_created,
        persons_created=result.persons_created,
        faces_clustered=result.faces_clustered,
        assignments_created=result.assignments_created,
        message="Unknown face clustering completed",
    )


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
