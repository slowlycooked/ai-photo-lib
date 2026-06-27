from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from ..config import settings
from ..models.photo import Photo
from ..models.project import Project

logger = logging.getLogger(__name__)

ORIGINAL_TRASH_MANIFEST = "pending-original-trash.jsonl"


@dataclass
class PhotoDeleteResult:
    project_id: int
    photo_id: int
    deleted_thumbnail: bool
    deleted_original: bool
    queued_original_for_trash: bool


@dataclass
class PhotoBatchDeleteResult:
    project_id: int
    requested_count: int
    deleted_count: int
    deleted_photo_ids: List[int]
    not_found_photo_ids: List[int]
    deleted_thumbnail_count: int
    deleted_original_count: int
    queued_original_for_trash_count: int


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


def _relative_library_path(photo: Photo, project: Project) -> str:
    if photo.relative_path:
        return photo.relative_path

    try:
        return str(
            Path(photo.file_path)
            .resolve()
            .relative_to(Path(project.photo_library_path).resolve())
        )
    except ValueError:
        return photo.file_name


def _ai_photo_data_root() -> Path:
    return Path(settings.thumbnail_path).expanduser().resolve().parent


def _queue_original_trash_request(db: Session, *, project_id: int, photo: Photo) -> bool:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if project is None:
        raise ValueError("Project not found")

    data_root = _ai_photo_data_root()
    data_root.mkdir(parents=True, exist_ok=True)
    manifest_path = data_root / ORIGINAL_TRASH_MANIFEST

    payload = {
        "version": 1,
        "action": "move_original_to_trash",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "project_name": project.name,
        "photo_id": photo.id,
        "file_name": photo.file_name,
        "relative_path": _relative_library_path(photo, project),
        "absolute_path": photo.file_path,
        "photo_library_path": project.photo_library_path,
        "thumbnail_path": photo.thumbnail_path,
        "file_hash": photo.file_hash,
        "file_size": photo.file_size,
        "mime_type": photo.mime_type,
        "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
    }

    with manifest_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        fh.write("\n")

    return True


def delete_photo_record(
    db: Session,
    *,
    project_id: int,
    photo: Photo,
    delete_original: bool = False,
) -> PhotoDeleteResult:
    """Delete a photo DB record and cleanup local thumbnail.

    When ``delete_original=True``, record the original file in a NAS-side
    trash manifest. The app never deletes original files directly.
    """
    if photo.project_id != project_id:
        raise ValueError("Photo does not belong to project")

    if delete_original:
        queued_original_for_trash = _queue_original_trash_request(
            db,
            project_id=project_id,
            photo=photo,
        )
    else:
        queued_original_for_trash = False

    deleted_thumbnail = _remove_file(photo.thumbnail_path)

    db.delete(photo)

    return PhotoDeleteResult(
        project_id=project_id,
        photo_id=photo.id,
        deleted_thumbnail=deleted_thumbnail,
        deleted_original=False,
        queued_original_for_trash=queued_original_for_trash,
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
            queued_original_for_trash_count=0,
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
    queued_original_for_trash_count = 0

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
        if result.queued_original_for_trash:
            queued_original_for_trash_count += 1

    return PhotoBatchDeleteResult(
        project_id=project_id,
        requested_count=len(unique_photo_ids),
        deleted_count=len(deleted_photo_ids),
        deleted_photo_ids=deleted_photo_ids,
        not_found_photo_ids=not_found_photo_ids,
        deleted_thumbnail_count=deleted_thumbnail_count,
        deleted_original_count=deleted_original_count,
        queued_original_for_trash_count=queued_original_for_trash_count,
    )
