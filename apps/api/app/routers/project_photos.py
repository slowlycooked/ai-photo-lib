from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_manager, require_project_photo
from ..database import get_db
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.ai import AIAnalysisResponse
from ..schemas.photo import (
    PhotoBatchDeleteRequest,
    PhotoBatchDeleteResponse,
    PhotoDeleteResponse,
    PhotoDetailResponse,
    PhotoListResponse,
)
from ..services.photo_cleanup_app_service import PhotoCleanupAppService
from ..services.project_photo_asset_service import (
    PhotoBytesAsset,
    PhotoPathOwnershipError,
    PhotoPreviewConversionError,
    ProjectPhotoAssetService,
)
from ..services.project_photos_query_service import ProjectPhotosQueryService

router = APIRouter(prefix="/projects", tags=["projects-photos"])


@router.get("/{project_id}/photos", response_model=PhotoListResponse)
def list_project_photos(
    project_id: int,
    page: int = 1,
    page_size: int = Query(50, ge=1, le=100),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """List photos for a specific project with optional filters."""
    total, photos = ProjectPhotosQueryService(db).list_photos(
        project_id=project_id,
        page=page,
        page_size=page_size,
        date_from=date_from,
        date_to=date_to,
        folder_id=folder_id,
        folder_scope=folder_scope,
    )
    page_size = max(1, min(page_size, 100))
    return PhotoListResponse(total=total, page=page, page_size=page_size, items=photos)


@router.get("/{project_id}/photos/timeline")
def get_project_timeline(
    project_id: int,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return monthly photo count timeline for a specific project."""
    items = ProjectPhotosQueryService(db).timeline(
        project_id=project_id,
        folder_id=folder_id,
        folder_scope=folder_scope,
    )
    return {"items": items}


@router.get("/{project_id}/photos/{photo_id}", response_model=PhotoDetailResponse)
def get_project_photo(
    photo: Photo = Depends(require_project_photo),
):
    """Return a single photo within project scope."""
    return photo


@router.get("/{project_id}/photos/{photo_id}/thumbnail")
def get_project_photo_thumbnail(
    project: Project = Depends(require_project),
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Serve or generate the thumbnail for a photo."""
    try:
        asset = ProjectPhotoAssetService(db).get_thumbnail_asset(project=project, photo=photo)
    except PhotoPathOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        asset.path,
        media_type=asset.media_type,
        headers=asset.headers,
    )


@router.get("/{project_id}/photos/{photo_id}/original")
def get_project_photo_original(
    project: Project = Depends(require_project),
    photo: Photo = Depends(require_project_photo),
):
    """Download the original file for a photo, scoped to its project."""
    try:
        asset = ProjectPhotoAssetService().get_original_asset(project=project, photo=photo)
    except PhotoPathOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        asset.path,
        media_type=asset.media_type,
        filename=asset.filename,
        headers=asset.headers,
    )


@router.get("/{project_id}/photos/{photo_id}/preview")
def get_project_photo_preview(
    project: Project = Depends(require_project),
    photo: Photo = Depends(require_project_photo),
):
    """Serve a browser-displayable version of the photo inline (no attachment).

    * JPEG/PNG/WebP/GIF/AVIF: returned as-is with inline Content-Disposition.
    * HEIC/HEIF and other non-web formats: converted to JPEG on the fly.
    """
    try:
        asset = ProjectPhotoAssetService().get_preview_asset(project=project, photo=photo)
    except PhotoPathOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhotoPreviewConversionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if isinstance(asset, PhotoBytesAsset):
        return Response(
            content=asset.content,
            media_type=asset.media_type,
            headers=asset.headers,
        )

    return FileResponse(
        asset.path,
        media_type=asset.media_type,
        headers=asset.headers,
    )


@router.get("/{project_id}/photos/{photo_id}/ai", response_model=AIAnalysisResponse)
def get_project_photo_ai(
    project_id: int,
    photo_id: int,
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Return the latest AI analysis for a photo within project scope."""
    analysis = ProjectPhotosQueryService(db).get_latest_ai_analysis(
        project_id=project_id,
        photo_id=photo_id,
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No AI analysis found for this photo")
    return analysis


@router.delete("/{project_id}/photos/{photo_id}", response_model=PhotoDeleteResponse)
def delete_project_photo(
    project_id: int,
    delete_original: bool = Query(False),
    _project: Project = Depends(require_project_manager),
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Delete a project photo record and cleanup thumbnail.

    Original file deletion is opt-in through ``delete_original=true``.
    """
    service = PhotoCleanupAppService(db)
    try:
        result = service.delete_photo_record(
            project_id=project_id,
            photo=photo,
            delete_original=delete_original,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Original file not found on disk")
    except PermissionError:
        raise HTTPException(status_code=403, detail="No permission to delete original file")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete original file: {exc}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Photo project mismatch")

    return PhotoDeleteResponse(
        project_id=result.project_id,
        photo_id=result.photo_id,
        deleted_thumbnail=result.deleted_thumbnail,
        deleted_original=result.deleted_original,
        message="Photo record deleted",
    )


@router.post("/{project_id}/photos/batch-delete", response_model=PhotoBatchDeleteResponse)
def batch_delete_project_photos(
    project_id: int,
    payload: PhotoBatchDeleteRequest,
    _project: Project = Depends(require_project_manager),
    db: Session = Depends(get_db),
):
    """Delete selected project photo records and optionally delete originals."""
    service = PhotoCleanupAppService(db)
    try:
        result = service.delete_photo_records_batch(
            project_id=project_id,
            photo_ids=payload.photo_ids,
            delete_original=payload.delete_original,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Original file not found on disk")
    except PermissionError:
        raise HTTPException(status_code=403, detail="No permission to delete original file")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete original file: {exc}")
    except ValueError:
        raise HTTPException(status_code=400, detail="Photo project mismatch")

    return PhotoBatchDeleteResponse(
        project_id=result.project_id,
        requested_count=result.requested_count,
        deleted_count=result.deleted_count,
        deleted_photo_ids=result.deleted_photo_ids,
        not_found_photo_ids=result.not_found_photo_ids,
        deleted_thumbnail_count=result.deleted_thumbnail_count,
        deleted_original_count=result.deleted_original_count,
        message="Batch photo deletion completed",
    )


@router.post("/{project_id}/photos/{photo_id}/delete", response_model=PhotoDeleteResponse)
def delete_project_photo_compat(
    project_id: int,
    delete_original: bool = Query(False),
    _project: Project = Depends(require_project_manager),
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Compatibility alias for photo deletion when DELETE is unavailable."""
    return delete_project_photo(
        project_id=project_id,
        delete_original=delete_original,
        _project=_project,
        photo=photo,
        db=db,
    )
