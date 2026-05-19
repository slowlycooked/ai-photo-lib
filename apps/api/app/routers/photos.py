from __future__ import annotations

import os
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from ..models.folder import ProjectFolder
from ..schemas.ai import AIAnalysisResponse
from ..schemas.photo import PhotoDetailResponse, PhotoListResponse, PhotoResponse
from ..services.folder_service import apply_folder_filter

router = APIRouter(prefix="/photos", tags=["photos"])


# ─── Timeline ────────────────────────────────────────────────────────────────

@router.get("/timeline")
def get_timeline(
    project_id: Optional[int] = None,
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    base_query = db.query(Photo).filter(Photo.deleted_at.is_(None), Photo.taken_at.is_not(None))
    if project_id is not None:
        base_query = base_query.filter(Photo.project_id == project_id)
    
    # 应用文件夹过滤
    if folder_id is not None and project_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    # 从 base_query 的 Photo 对象执行聚合
    rows = (
        base_query
        .with_entities(
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

    items = [
        {
            "key": f"{int(row.year)}-{str(int(row.month)).zfill(2)}",
            "year": int(row.year),
            "month": int(row.month),
            "count": row.count,
        }
        for row in rows
    ]
    return {"items": items}


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=PhotoListResponse)
def list_photos(
    page: int = 1,
    page_size: int = 50,
    project_id: Optional[int] = None,
    date_from: Optional[date] = Query(
        None, description="Filter photos taken on/after this date (YYYY-MM-DD)"
    ),
    date_to: Optional[date] = Query(
        None, description="Filter photos taken before this date (exclusive, YYYY-MM-DD)"
    ),
    folder_id: Optional[int] = None,
    folder_scope: str = "subtree",
    db: Session = Depends(get_db),
):
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    base_query = db.query(Photo).filter(Photo.deleted_at.is_(None))
    if project_id is not None:
        base_query = base_query.filter(Photo.project_id == project_id)
    if date_from is not None:
        base_query = base_query.filter(
            Photo.taken_at >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        base_query = base_query.filter(
            Photo.taken_at < datetime.combine(date_to, time.min)
        )
    
    # 应用文件夹过滤
    if folder_id is not None and project_id is not None:
        base_query = apply_folder_filter(base_query, db, project_id, folder_id, folder_scope)

    total = base_query.count()
    photos = (
        base_query
        .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return PhotoListResponse(total=total, page=page, page_size=page_size, items=photos)


# ─── Get one ──────────────────────────────────────────────────────────────────

@router.get("/{photo_id}", response_model=PhotoDetailResponse)
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.deleted_at.is_(None))
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


# ─── Thumbnail ────────────────────────────────────────────────────────────────

@router.get("/{photo_id}/thumbnail")
def get_thumbnail(photo_id: int, db: Session = Depends(get_db)):
    from ..services.thumbnail import generate_thumbnail

    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.deleted_at.is_(None))
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Generate on-the-fly if thumbnail is missing (e.g. HEIC added before pillow-heif)
    if not photo.thumbnail_path or not os.path.exists(photo.thumbnail_path):
        if not os.path.exists(photo.file_path):
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        thumb = generate_thumbnail(photo.file_path)
        if not thumb:
            raise HTTPException(status_code=404, detail="Thumbnail not available")
        photo.thumbnail_path = thumb
        db.commit()

    return FileResponse(
        photo.thumbnail_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


# ─── Original download ────────────────────────────────────────────────────────

@router.get("/{photo_id}/original")
def get_original(photo_id: int, db: Session = Depends(get_db)):
    """Download the original photo file. Path is resolved from DB only — no
    caller-supplied paths are accepted, preventing path-traversal attacks."""
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.deleted_at.is_(None))
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

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


# ─── AI analysis ──────────────────────────────────────────────────────────────

@router.get("/{photo_id}/ai", response_model=AIAnalysisResponse)
def get_photo_ai(photo_id: int, db: Session = Depends(get_db)):
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.deleted_at.is_(None))
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    analysis = (
        db.query(PhotoAIAnalysis)
        .filter(PhotoAIAnalysis.photo_id == photo_id)
        .order_by(PhotoAIAnalysis.created_at.desc())
        .first()
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="No AI analysis found for this photo")
    return analysis
