from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.ai import PhotoAIAnalysis
from ..models.photo import Photo
from ..schemas.ai import AIAnalysisResponse
from ..schemas.photo import PhotoDetailResponse, PhotoListResponse, PhotoResponse

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("", response_model=PhotoListResponse)
def list_photos(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size

    base_query = db.query(Photo).filter(Photo.deleted_at.is_(None))
    total = base_query.count()
    photos = (
        base_query
        .order_by(Photo.taken_at.desc().nullslast(), Photo.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return PhotoListResponse(total=total, page=page, page_size=page_size, items=photos)


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


@router.get("/{photo_id}/thumbnail")
def get_thumbnail(photo_id: int, db: Session = Depends(get_db)):
    photo = (
        db.query(Photo)
        .filter(Photo.id == photo_id, Photo.deleted_at.is_(None))
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not photo.thumbnail_path or not os.path.exists(photo.thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not available")
    return FileResponse(
        photo.thumbnail_path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
