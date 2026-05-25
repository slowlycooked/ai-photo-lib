from __future__ import annotations

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
from ..repositories.unit_of_work import UnitOfWork
from ..schemas.face import (
    FaceClusterUnknownRequest,
    FaceClusterUnknownResponse,
    FaceDetectionDetailResponse,
    FaceDetectionListResponse,
    FaceDetectionResponse,
    FaceScanProjectStartResponse,
    FaceScanProjectStatusResponse,
    FaceScanResponse,
)
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
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanProjectStartResponse:
    settings = get_or_create_project_face_settings(db, project_id)
    if not settings.face_recognition_enabled:
        raise HTTPException(
            status_code=409,
            detail="Face recognition is disabled for this project. Enable it in face settings first.",
        )

    active_face_scan_photo_ids = (
        db.query(AIJob.photo_id)
        .filter(
            AIJob.project_id == project_id,
            AIJob.job_type == "face_scan",
            AIJob.status.in_(["queued", "running"]),
        )
        .subquery()
    )

    candidate_photo_ids = [
        row[0]
        for row in (
            db.query(Photo.id)
            .filter(
                Photo.project_id == project_id,
                Photo.deleted_at.is_(None),
                Photo.id.not_in(sa.select(active_face_scan_photo_ids.c.photo_id)),
            )
            .order_by(Photo.id.asc())
            .all()
        )
    ]

    active_count = (
        db.query(sa.func.count(AIJob.id))
        .filter(
            AIJob.project_id == project_id,
            AIJob.job_type == "face_scan",
            AIJob.status.in_(["queued", "running"]),
        )
        .scalar()
        or 0
    )

    if candidate_photo_ids:
        uow = UnitOfWork(db)
        uow.ai_jobs.enqueue_bulk(project_id, candidate_photo_ids, job_type="face_scan")
        uow.commit()

    return FaceScanProjectStartResponse(
        project_id=project_id,
        created_jobs=len(candidate_photo_ids),
        skipped_active_jobs=int(active_count),
        message="Project face scan jobs created",
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
    rows = (
        db.query(AIJob.status, sa.func.count(AIJob.id))
        .filter(
            AIJob.project_id == project_id,
            AIJob.job_type == "face_scan",
        )
        .group_by(AIJob.status)
        .all()
    )
    counts = {status: int(count) for status, count in rows}
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
    return FileResponse(
        face.face_crop_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
