from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional, Sequence

from sqlalchemy.orm import Session

from ..config import settings
from ..models.derivative import PhotoDerivative
from ..models.photo import Photo
from ..models.project import Project
from .project_library_service import get_project_library_paths

logger = logging.getLogger(__name__)

ORIGINAL_TRASH_MANIFEST = "pending-original-trash.jsonl"
# Must mirror scripts/deleteMartinLib.sh: the NAS batch worker takes this
# lock directory before extracting the manifest, so the app-side append and
# the app-side cancel both stay mutually exclusive with the NAS batch.
ORIGINAL_TRASH_LOCK_DIR = ".original-trash.lock"
ORIGINAL_TRASH_PROCESSING_GLOB = "pending-original-trash.processing-*.jsonl"
_APPEND_LOCK_WAIT_SECONDS = 1.0


class PhotoCleanupError(RuntimeError):
    pass


class PhotoCleanupConflict(PhotoCleanupError):
    pass


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


def _relative_library_path(photo: Photo, library_paths: List[str]) -> str:
    if photo.relative_path:
        return photo.relative_path

    resolved = Path(photo.file_path).resolve()
    for root in library_paths:
        try:
            return str(resolved.relative_to(Path(root).resolve()))
        except ValueError:
            continue
    return photo.file_name


def _matching_library_root(library_paths: List[str], file_path: str) -> Optional[str]:
    """Return the configured root that contains ``file_path``, if any."""
    resolved = Path(file_path).resolve()
    for root in library_paths:
        try:
            resolved.relative_to(Path(root).resolve())
            return root
        except ValueError:
            continue
    return None


def _ai_photo_data_root() -> Path:
    return Path(settings.thumbnail_path).expanduser().resolve().parent


@contextmanager
def _original_trash_lock(*, wait_seconds: float = 0.0) -> Iterator[bool]:
    """Best-effort acquisition of the NAS worker's manifest lock directory.

    Yields ``True`` when the lock was acquired (and always releases it after).
    Yields ``False`` when the lock is held elsewhere; callers decide whether
    that is fatal (cancel) or acceptable (append during a long NAS batch).
    """
    lock_dir = _ai_photo_data_root() / ORIGINAL_TRASH_LOCK_DIR
    acquired = False
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            lock_dir.mkdir(parents=True, exist_ok=False)
            acquired = True
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        except OSError:
            break
    try:
        yield acquired
    finally:
        if acquired:
            try:
                lock_dir.rmdir()
            except OSError:
                logger.warning(
                    "Failed to release original-trash manifest lock: %s",
                    lock_dir,
                    exc_info=True,
                )


def _manifest_entry_matches(
    entry: object, *, project_id: int, photo_id: int
) -> bool:
    return (
        isinstance(entry, dict)
        and entry.get("action") == "move_original_to_trash"
        and entry.get("project_id") == project_id
        and entry.get("photo_id") == photo_id
    )


def _entry_claimed_by_processing_manifests(
    data_root: Path, *, project_id: int, photo_id: int
) -> bool:
    """Return True when a processing-*.jsonl batch already claims the entry."""
    for processing in sorted(data_root.glob(ORIGINAL_TRASH_PROCESSING_GLOB)):
        try:
            lines = processing.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.warning(
                "Failed to inspect processing manifest: %s", processing, exc_info=True
            )
            return True  # fail closed: refuse to cancel what we cannot inspect
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if _manifest_entry_matches(entry, project_id=project_id, photo_id=photo_id):
                logger.info(
                    "Original trash entry claimed by processing manifest %s",
                    processing.name,
                )
                return True
    return False


def _rewrite_manifest(manifest_path: Path, entries: Sequence[str]) -> None:
    """Atomically replace the manifest with the surviving JSON lines."""
    tmp_path = manifest_path.with_name(f"{manifest_path.name}.cancel-{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        for line in entries:
            fh.write(line)
            fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, manifest_path)
    try:
        dir_fd = os.open(manifest_path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        logger.warning("Failed to fsync manifest directory", exc_info=True)
    finally:
        os.close(dir_fd)


def cancel_original_trash_request(db: Session, *, project_id: int, photo: Photo) -> bool:
    """Withdraw a pending original-photo deletion request from the NAS manifest.

    Runs under the same lock the NAS batch worker takes, so an entry can never
    be cancelled while the batch is extracting or processing it. Returns
    ``True`` when a pending entry was removed and ``False`` when no pending
    entry existed (nothing left to cancel on the NAS side).
    """
    data_root = _ai_photo_data_root()
    manifest_path = data_root / ORIGINAL_TRASH_MANIFEST

    with _original_trash_lock() as acquired:
        if not acquired:
            raise PhotoCleanupConflict(
                "NAS 删除批处理可能正在进行（或锁目录未清理），暂时无法撤销删除请求"
            )
        if _entry_claimed_by_processing_manifests(
            data_root, project_id=project_id, photo_id=photo.id
        ):
            raise PhotoCleanupConflict(
                "删除请求已被 NAS 批处理提取，无法撤销；请等待批处理结束或检查回收站"
            )
        if not manifest_path.exists():
            return False

        kept_lines: List[str] = []
        removed = False
        with manifest_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = json.loads(stripped)
                except json.JSONDecodeError:
                    kept_lines.append(stripped)
                    continue
                if _manifest_entry_matches(
                    entry, project_id=project_id, photo_id=photo.id
                ):
                    removed = True
                    continue
                kept_lines.append(stripped)
        if not removed:
            return False
        _rewrite_manifest(manifest_path, kept_lines)
        logger.info(
            "Cancelled pending original trash request project_id=%d photo_id=%d",
            project_id,
            photo.id,
        )
        return True


def queue_original_trash_request(db: Session, *, project_id: int, photo: Photo) -> bool:
    """Append an original-photo deletion request for the NAS-side worker.

    The application never moves or deletes an original photo directly. Both the
    regular photo-delete flow and the quarantine review flow use this manifest
    boundary so the NAS-side script remains the only original-file mutator.
    """
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

    library_paths = get_project_library_paths(db, project)

    payload = {
        "version": 1,
        "action": "move_original_to_trash",
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "project_name": project.name,
        "photo_id": photo.id,
        "file_name": photo.file_name,
        "relative_path": _relative_library_path(photo, library_paths),
        "library_path": _matching_library_root(library_paths, photo.file_path),
        "file_hash": photo.file_hash,
        "file_size": photo.file_size,
        "mime_type": photo.mime_type,
        "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
    }

    with _original_trash_lock(wait_seconds=_APPEND_LOCK_WAIT_SECONDS) as lock_acquired:
        if not lock_acquired:
            logger.info(
                "Proceeding to append trash request without manifest lock "
                "project_id=%d photo_id=%d",
                project_id,
                photo.id,
            )
        with manifest_path.open("a+", encoding="utf-8") as fh:
            fh.seek(0)
            for line in fh:
                try:
                    existing = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    existing.get("action") == payload["action"]
                    and existing.get("project_id") == project_id
                    and existing.get("photo_id") == photo.id
                ):
                    return True

            fh.seek(0, os.SEEK_END)
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())

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
        queued_original_for_trash = queue_original_trash_request(
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
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
            Photo.status != "quarantined",
        )
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


def rebuild_project_photo_index(
    db: Session,
    *,
    project_id: int,
    batch_size: int = 100,
) -> int:
    """Delete one project's stale photo index without touching original files.

    Photo-owned database rows are removed by foreign-key cascades. Cached
    thumbnails and derivative files are removed explicitly because the newly
    scanned photos receive new IDs and therefore cannot reuse those files.
    """
    photos = db.query(Photo).filter(Photo.project_id == project_id).all()
    if not photos:
        return 0

    photo_ids = [photo.id for photo in photos]
    derivative_paths = (
        db.query(PhotoDerivative.path)
        .filter(
            PhotoDerivative.project_id == project_id,
            PhotoDerivative.photo_id.in_(photo_ids),
        )
        .all()
    )
    for (path,) in derivative_paths:
        _remove_file(path)

    deleted_count = 0
    pending = 0
    for photo in photos:
        _remove_file(photo.thumbnail_path)
        db.delete(photo)
        deleted_count += 1
        pending += 1
        if pending >= batch_size:
            db.commit()
            pending = 0

    if pending > 0:
        db.commit()

    logger.info(
        "Rebuild removed %d stale photo index records for project_id=%d",
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
