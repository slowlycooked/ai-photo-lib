from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from ..models.photo import Photo

logger = logging.getLogger(__name__)


@dataclass
class PhotoDeleteResult:
    project_id: int
    photo_id: int
    deleted_thumbnail: bool
    deleted_original: bool


@dataclass
class PhotoBatchDeleteResult:
    project_id: int
    requested_count: int
    deleted_count: int
    deleted_photo_ids: List[int]
    not_found_photo_ids: List[int]
    deleted_thumbnail_count: int
    deleted_original_count: int


def _remove_file(path: Optional[str], *, raise_on_error: bool = False) -> bool:
    if not path:
        return False

    target = Path(path)
    if not target.exists():
        return False

    try:
        target.unlink()
        return True
    except Exception:
        if raise_on_error:
            raise
        logger.warning("Failed to remove file: %s", path, exc_info=True)
        return False


def delete_photo_record(
    db: Session,
    *,
    project_id: int,
    photo: Photo,
    delete_original: bool = False,
) -> PhotoDeleteResult:
    """Delete a photo DB record and cleanup local thumbnail.

    The original file is only deleted when ``delete_original=True``.
    """
    if photo.project_id != project_id:
        raise ValueError("Photo does not belong to project")

    deleted_original = False
    if delete_original:
        deleted_original = _remove_file(photo.file_path, raise_on_error=True)

    deleted_thumbnail = _remove_file(photo.thumbnail_path)

    db.delete(photo)

    return PhotoDeleteResult(
        project_id=project_id,
        photo_id=photo.id,
        deleted_thumbnail=deleted_thumbnail,
        deleted_original=deleted_original,
    )


def cleanup_missing_project_photos(
    db: Session,
    *,
    project_id: int,
    batch_size: int = 100,
) -> int:
    """Remove records for files no longer present in local library.

    Also removes stale thumbnails for those records.
    """
    deleted_count = 0
    pending = 0

    photos = (
        db.query(Photo)
        .filter(Photo.project_id == project_id, Photo.deleted_at.is_(None))
        .all()
    )

    for photo in photos:
        if Path(photo.file_path).exists():
            continue

        _remove_file(photo.thumbnail_path)
        db.delete(photo)
        deleted_count += 1
        pending += 1

        if pending >= batch_size:
            db.commit()
            pending = 0

    if pending > 0:
        db.commit()

    if deleted_count > 0:
        logger.info(
            "Cleanup removed %d missing photo records for project_id=%d",
            deleted_count,
            project_id,
        )

    return deleted_count


def delete_photo_records_batch(
    db: Session,
    *,
    project_id: int,
    photo_ids: Sequence[int],
    delete_original: bool = False,
) -> PhotoBatchDeleteResult:
    unique_photo_ids: List[int] = list(dict.fromkeys(int(photo_id) for photo_id in photo_ids))
    if not unique_photo_ids:
        return PhotoBatchDeleteResult(
            project_id=project_id,
            requested_count=0,
            deleted_count=0,
            deleted_photo_ids=[],
            not_found_photo_ids=[],
            deleted_thumbnail_count=0,
            deleted_original_count=0,
        )

    photos = (
        db.query(Photo)
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.id.in_(unique_photo_ids),
        )
        .all()
    )
    photos_by_id = {photo.id: photo for photo in photos}

    deleted_photo_ids: List[int] = []
    not_found_photo_ids: List[int] = []
    deleted_thumbnail_count = 0
    deleted_original_count = 0

    for photo_id in unique_photo_ids:
        photo = photos_by_id.get(photo_id)
        if photo is None:
            not_found_photo_ids.append(photo_id)
            continue

        result = delete_photo_record(
            db,
            project_id=project_id,
            photo=photo,
            delete_original=delete_original,
        )
        deleted_photo_ids.append(result.photo_id)
        if result.deleted_thumbnail:
            deleted_thumbnail_count += 1
        if result.deleted_original:
            deleted_original_count += 1

    return PhotoBatchDeleteResult(
        project_id=project_id,
        requested_count=len(unique_photo_ids),
        deleted_count=len(deleted_photo_ids),
        deleted_photo_ids=deleted_photo_ids,
        not_found_photo_ids=not_found_photo_ids,
        deleted_thumbnail_count=deleted_thumbnail_count,
        deleted_original_count=deleted_original_count,
    )
