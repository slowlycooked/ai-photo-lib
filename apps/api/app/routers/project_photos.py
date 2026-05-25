from __future__ import annotations

import io
import os
from datetime import date, datetime, time as time_
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..api.deps import require_project, require_project_photo
from ..database import get_db
from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from ..models.project import Project
from ..schemas.ai import AIAnalysisResponse
from ..schemas.photo import PhotoDeleteResponse, PhotoDetailResponse, PhotoListResponse
from ..services.folder_service import apply_folder_filter
from ..services.photo_cleanup import delete_photo_record
from ..services.thumbnail import generate_thumbnail

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
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    base_query = db.query(Photo).filter(
        Photo.project_id == project_id, Photo.deleted_at.is_(None)
    )
    if date_from is not None:
        base_query = base_query.filter(
            Photo.taken_at >= datetime.combine(date_from, time_.min)
        )
    if date_to is not None:
        base_query = base_query.filter(
            Photo.taken_at < datetime.combine(date_to, time_.min)
        )
    if folder_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    total = base_query.count()
    photos = (
        base_query.order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
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
    base_query = db.query(Photo).filter(
        Photo.project_id == project_id,
        Photo.deleted_at.is_(None),
        Photo.taken_at.is_not(None),
    )
    if folder_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    rows = (
        base_query.with_entities(
            extract("year", Photo.taken_at).label("year"),
            extract("month", Photo.taken_at).label("month"),
            func.count(Photo.id).label("count"),
        )
        .group_by("year", "month")
        .order_by(
            extract("year", Photo.taken_at).desc(),
            extract("month", Photo.taken_at).desc(),
        )
        .all()
    )
    return {
        "items": [
            {
                "key": f"{int(r.year)}-{str(int(r.month)).zfill(2)}",
                "year": int(r.year),
                "month": int(r.month),
                "count": r.count,
            }
            for r in rows
        ]
    }


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
    if not photo.thumbnail_path or not os.path.exists(photo.thumbnail_path):
        if not os.path.exists(photo.file_path):
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        thumb = generate_thumbnail(
            photo.file_path,
            project_id=project.id,
            thumbnail_root=project.thumbnail_path,
        )
        if not thumb:
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        photo.thumbnail_path = thumb
        db.commit()

    return FileResponse(
        photo.thumbnail_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@router.get("/{project_id}/photos/{photo_id}/original")
def get_project_photo_original(
    photo: Photo = Depends(require_project_photo),
):
    """Download the original file for a photo, scoped to its project."""
    if not os.path.exists(photo.file_path):
        raise HTTPException(status_code=404, detail="Original file not found on disk")

    return FileResponse(
        photo.file_path,
        media_type=photo.mime_type or "application/octet-stream",
        filename=photo.file_name,
        headers={
            "Cache-Control": "private, max-age=0",
            "Content-Disposition": f'attachment; filename="{photo.file_name}"',
        },
    )


# Browser-renderable MIME types — served inline for preview
_INLINE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
# Non-browser-renderable suffixes that need JPEG conversion before preview
_CONVERT_SUFFIXES = {".heic", ".heif"}


@router.get("/{project_id}/photos/{photo_id}/preview")
def get_project_photo_preview(
    photo: Photo = Depends(require_project_photo),
):
    """Serve a browser-displayable version of the photo inline (no attachment).

    * JPEG/PNG/WebP/GIF/AVIF: returned as-is with inline Content-Disposition.
    * HEIC/HEIF and other non-web formats: converted to JPEG on the fly.
    """
    if not os.path.exists(photo.file_path):
        raise HTTPException(status_code=404, detail="Original file not found on disk")

    suffix = Path(photo.file_path).suffix.lower()
    mime = photo.mime_type or ""

    if mime in _INLINE_MIME and suffix not in _CONVERT_SUFFIXES:
        # Serve directly — browser can render this natively
        return FileResponse(
            photo.file_path,
            media_type=mime,
            headers={
                "Cache-Control": "private, max-age=3600",
                "Content-Disposition": "inline",
            },
        )

    # Convert to JPEG in memory (covers HEIC, HEIF, and unknown formats)
    try:
        from PIL import Image  # pillow-heif is already registered at startup

        with Image.open(photo.file_path) as img:
            img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90, optimize=True)
            jpeg_bytes = buf.getvalue()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Preview conversion failed: {exc}",
        ) from exc

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@router.get("/{project_id}/photos/{photo_id}/ai", response_model=AIAnalysisResponse)
def get_project_photo_ai(
    project_id: int,
    photo_id: int,
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Return the latest AI analysis for a photo within project scope."""
    analysis = (
        db.query(PhotoAIAnalysis)
        .filter(
            PhotoAIAnalysis.photo_id == photo_id,
            PhotoAIAnalysis.project_id == project_id,
        )
        .order_by(PhotoAIAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No AI analysis found for this photo")
    return analysis


@router.delete("/{project_id}/photos/{photo_id}", response_model=PhotoDeleteResponse)
def delete_project_photo(
    project_id: int,
    delete_original: bool = Query(False),
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Delete a project photo record and cleanup thumbnail.

    Original file deletion is opt-in through ``delete_original=true``.
    """
    try:
        result = delete_photo_record(
            db,
            project_id=project_id,
            photo=photo,
            delete_original=delete_original,
        )
        db.commit()
    except FileNotFoundError:
        db.rollback()
        raise HTTPException(status_code=404, detail="Original file not found on disk")
    except PermissionError:
        db.rollback()
        raise HTTPException(status_code=403, detail="No permission to delete original file")
    except OSError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete original file: {exc}")
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Photo project mismatch")

    return PhotoDeleteResponse(
        project_id=result.project_id,
        photo_id=result.photo_id,
        deleted_thumbnail=result.deleted_thumbnail,
        deleted_original=result.deleted_original,
        message="Photo record deleted",
    )


@router.post("/{project_id}/photos/{photo_id}/delete", response_model=PhotoDeleteResponse)
def delete_project_photo_compat(
    project_id: int,
    delete_original: bool = Query(False),
    photo: Photo = Depends(require_project_photo),
    db: Session = Depends(get_db),
):
    """Compatibility alias for photo deletion when DELETE is unavailable."""
    return delete_project_photo(
        project_id=project_id,
        delete_original=delete_original,
        photo=photo,
        db=db,
    )
