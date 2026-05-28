from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project, require_project_photo
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.face import (
    FaceClusterUnknownRequest,
    FaceClusterUnknownResponse,
    FaceClusterUnknownStatusResponse,
    FaceDetectionDetailResponse,
    FaceDetectionListResponse,
    FaceDetectionResponse,
    FaceRematchUnknownRequest,
    FaceRematchUnknownResponse,
    FaceRematchUnknownStatusResponse,
    FaceScanProjectStartRequest,
    FaceScanProjectStartResponse,
    FaceScanProjectStatusResponse,
    FaceScanResponse,
)
from ..services.project_face_cluster_rematch_app_service import (
    FaceClusterTaskNotFoundError,
    FaceRematchTaskNotFoundError,
    FaceRematchValidationError,
    ProjectFaceClusterRematchAppService,
)
from ..services.project_face_scan_project_app_service import (
    FaceScanProjectDisabledError,
    FaceScanProjectTaskNotFoundError,
    FaceScanProjectValidationError,
    ProjectFaceScanProjectAppService,
)
from ..services.project_manual_face_scan_app_service import (
    ManualFaceScanConflictError,
    ManualFaceScanPhotoNotFoundError,
    ManualFaceScanProviderUnavailableError,
    ProjectManualFaceScanAppService,
)
from ..services.project_faces_query_service import (
    FaceCropNotFoundError,
    FaceNotFoundError,
    ProjectFacesQueryService,
)
from ..services.face_scan_service import FaceScanService
from ..services.unknown_face_clustering_service import cluster_unknown_faces

router = APIRouter(prefix="/projects", tags=["project-faces"])


@router.post("/{project_id}/photos/{photo_id}/face-scan", response_model=FaceScanResponse)
def scan_project_photo_faces(
    project_id: int,
    photo: Photo = Depends(require_project_photo),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanResponse:
    app_service = ProjectManualFaceScanAppService(
        db,
        scan_photo_fn=FaceScanService(db).scan_photo,
        cluster_unknown_faces_fn=cluster_unknown_faces,
    )
    try:
        return app_service.scan_project_photo(project_id=project_id, photo_id=photo.id)
    except ManualFaceScanConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ManualFaceScanProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ManualFaceScanPhotoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    service = ProjectFaceScanProjectAppService(db)
    try:
        return service.start(
            project_id=project_id,
            body=body or FaceScanProjectStartRequest(),
        )
    except FaceScanProjectDisabledError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FaceScanProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{project_id}/face-scan-project/status",
    response_model=FaceScanProjectStatusResponse,
)
def get_project_face_scan_job_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanProjectStatusResponse:
    return ProjectFaceScanProjectAppService(db).status(project_id=project_id)


@router.post(
    "/{project_id}/face-scan-project/cancel",
    response_model=FaceScanProjectStatusResponse,
)
def cancel_project_face_scan_jobs(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceScanProjectStatusResponse:
    try:
        return ProjectFaceScanProjectAppService(db).cancel(project_id=project_id)
    except FaceScanProjectTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    return ProjectFaceClusterRematchAppService(db).enqueue_cluster(
        project_id=project_id,
        max_faces=body.max_faces,
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
    return ProjectFaceClusterRematchAppService(db).cluster_status(project_id=project_id)


@router.post(
    "/{project_id}/face-cluster-unknown/cancel",
    response_model=FaceClusterUnknownStatusResponse,
)
def cancel_cluster_project_unknown_faces(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceClusterUnknownStatusResponse:
    try:
        return ProjectFaceClusterRematchAppService(db).cancel_cluster(project_id=project_id)
    except FaceClusterTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{project_id}/face-rematch-unknown",
    response_model=FaceRematchUnknownResponse,
)
def rematch_project_unknown_faces(
    project_id: int,
    body: FaceRematchUnknownRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceRematchUnknownResponse:
    try:
        return ProjectFaceClusterRematchAppService(db).enqueue_rematch(
            project_id=project_id,
            max_faces=body.max_faces,
            scope=body.scope,
            person_id=body.person_id,
            start_time=body.start_time,
            end_time=body.end_time,
        )
    except FaceRematchValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{project_id}/face-rematch-unknown/status",
    response_model=FaceRematchUnknownStatusResponse,
)
def get_rematch_project_unknown_faces_status(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceRematchUnknownStatusResponse:
    return ProjectFaceClusterRematchAppService(db).rematch_status(project_id=project_id)


@router.post(
    "/{project_id}/face-rematch-unknown/cancel",
    response_model=FaceRematchUnknownStatusResponse,
)
def cancel_rematch_project_unknown_faces(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> FaceRematchUnknownStatusResponse:
    try:
        return ProjectFaceClusterRematchAppService(db).cancel_rematch(project_id=project_id)
    except FaceRematchTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
    total, items = ProjectFacesQueryService(db).list_faces(
        project_id=project_id,
        page=page,
        page_size=page_size,
        photo_id=photo_id,
        status=status,
    )
    page_size = max(1, min(page_size, 200))
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
    try:
        face, embeddings = ProjectFacesQueryService(db).get_face_detail(
            project_id=project_id,
            face_id=face_id,
        )
    except FaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

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
    try:
        crop_path = ProjectFacesQueryService(db).get_face_crop_path(
            project_id=project_id,
            face_id=face_id,
        )
    except FaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FaceCropNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        str(crop_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
