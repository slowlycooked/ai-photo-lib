from __future__ import annotations

import hashlib
import io
import logging
import mimetypes
import tempfile
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Optional, Tuple

import exifread
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..config import settings
from ..models.photo import Photo
from .thumbnail import SUPPORTED_SUFFIXES, generate_thumbnail
from .path_utils import build_relative_paths
from .folder_service import ensure_folder_path
from .location_service import resolve_photo_location
from .photo_cleanup import cleanup_missing_project_photos

logger = logging.getLogger(__name__)

ScanProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ExistingPhotoSnapshot:
    file_hash: Optional[str]
    thumbnail_path: Optional[str]
    relative_path: Optional[str]
    folder_path: Optional[str]


@dataclass(frozen=True)
class PreparedScanFile:
    path: Path
    path_str: str
    relative_path: Optional[str]
    folder_path: Optional[str]
    file_hash: str
    file_size: int
    mime_type: Optional[str]
    width: Optional[int]
    height: Optional[int]
    exif: StructuredExif
    thumbnail_path: Optional[str]
    action: str
    latency_ms: int


# ---------------------------------------------------------------------------
# Scan state management
# ---------------------------------------------------------------------------

def _empty_state() -> dict[str, Any]:
    return {
        "running": False,
        "scanned": 0,
        "discovered_count": 0,
        "prepared_count": 0,
        "persisted_count": 0,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "current_stage": None,
        "current_path": None,
        "queue_depth": 0,
        "last_stage_latency_ms": None,
        "message": "idle",
        "recent_errors": [],
        "recent_files": [],
    }


def _push_scan_error(state: dict[str, Any], message: str, *, limit: int = 20) -> None:
    errors = state.setdefault("recent_errors", [])
    errors.append(message)
    if len(errors) > limit:
        del errors[:-limit]


def _push_file_progress(
    state: dict[str, Any],
    *,
    path: str,
    status: str,
    message: Optional[str] = None,
    limit: int = 100,
) -> None:
    entries = state.setdefault("recent_files", [])
    entries.append(
        {
            "path": path,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    if len(entries) > limit:
        del entries[:-limit]


def _snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "running": bool(state.get("running")),
        "scanned": int(state.get("scanned") or 0),
        "discovered_count": int(state.get("discovered_count") or 0),
        "prepared_count": int(state.get("prepared_count") or 0),
        "persisted_count": int(state.get("persisted_count") or 0),
        "inserted": int(state.get("inserted") or 0),
        "updated": int(state.get("updated") or 0),
        "errors": int(state.get("errors") or 0),
        "current_stage": state.get("current_stage"),
        "current_path": state.get("current_path"),
        "queue_depth": int(state.get("queue_depth") or 0),
        "last_stage_latency_ms": state.get("last_stage_latency_ms"),
        "message": str(state.get("message") or "idle"),
        "recent_errors": list(state.get("recent_errors") or []),
        "recent_files": list(state.get("recent_files") or []),
    }


def _set_scan_stage(
    state: dict[str, Any],
    *,
    stage: str,
    current_path: Optional[str] = None,
    queue_depth: Optional[int] = None,
    latency_ms: Optional[int] = None,
) -> None:
    state["current_stage"] = stage
    if current_path is not None:
        state["current_path"] = current_path
    if queue_depth is not None:
        state["queue_depth"] = max(0, int(queue_depth))
    if latency_ms is not None:
        state["last_stage_latency_ms"] = int(latency_ms)


def _emit_progress(
    state: dict[str, Any],
    progress_callback: Optional[ScanProgressCallback],
) -> None:
    if progress_callback is not None:
        progress_callback(_snapshot_state(state))


def _mark_persisted(state: dict[str, Any], *, path: str, latency_ms: int) -> None:
    _set_scan_stage(
        state,
        stage="persist",
        current_path=path,
        latency_ms=latency_ms,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_exif_dt(tags: dict) -> Optional[datetime]:
    for key in ("EXIF DateTimeOriginal", "Image DateTime", "EXIF DateTimeDigitized"):
        if key in tags:
            try:
                return datetime.strptime(str(tags[key]), "%Y:%m:%d %H:%M:%S")
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# GPS helpers
# ---------------------------------------------------------------------------

def _ratio_to_float(value) -> float:
    """Convert an exifread IfdTag ratio or 'num/den' string to a Python float."""
    if hasattr(value, "num") and hasattr(value, "den"):
        if value.den == 0:
            return 0.0
        return float(value.num) / float(value.den)
    s = str(value)
    if "/" in s:
        parts = s.split("/", 1)
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _dms_to_decimal(dms_tag, ref: str) -> Optional[float]:
    """Convert a DMS IfdTag (list of 3 ratios) plus a reference letter to decimal degrees."""
    if dms_tag is None:
        return None
    values = getattr(dms_tag, "values", None)
    if not values or len(values) != 3:
        return None
    degrees = _ratio_to_float(values[0])
    minutes = _ratio_to_float(values[1])
    seconds = _ratio_to_float(values[2])
    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return decimal


@dataclass
class StructuredExif:
    raw: Optional[Dict] = None
    taken_at: Optional[datetime] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_altitude: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    focal_length: Optional[str] = None
    aperture: Optional[str] = None
    exposure_time: Optional[str] = None
    iso: Optional[int] = None
    orientation: Optional[int] = None


def _extract_exif(path: str) -> StructuredExif:
    result = StructuredExif()
    try:
        suffix = Path(path).suffix.lower()
        if suffix in (".heic", ".heif"):
            # exifread cannot parse the HEIC/HEIF container format directly
            # (no JPEG/TIFF magic bytes at offset 0).  Use Pillow+pillow_heif to
            # pull the raw EXIF app-segment bytes out of the container, then feed
            # them to exifread so all existing tag-parsing logic is reused.
            with Image.open(path) as _img:
                exif_bytes: bytes = _img.info.get("exif", b"")
            if not exif_bytes:
                return result
            # Pillow wraps the TIFF data with an "Exif\x00\x00" APP1 prefix.
            # exifread only accepts bare TIFF (II/MM) or JPEG (FFD8) streams —
            # strip the prefix so the TIFF magic is at offset 0.
            if exif_bytes.startswith(b"Exif\x00\x00"):
                exif_bytes = exif_bytes[6:]
            fh: io.IOBase = io.BytesIO(exif_bytes)
        else:
            fh = open(path, "rb")

        with fh:
            tags = exifread.process_file(fh, stop_tag="UNDEF", details=False)
        if not tags:
            return result

        result.raw = {k: str(v) for k, v in tags.items() if not k.startswith("Thumbnail")}
        result.taken_at = _parse_exif_dt(tags)

        # GPS
        result.gps_latitude = _dms_to_decimal(
            tags.get("GPS GPSLatitude"),
            str(tags.get("GPS GPSLatitudeRef", "")),
        )
        result.gps_longitude = _dms_to_decimal(
            tags.get("GPS GPSLongitude"),
            str(tags.get("GPS GPSLongitudeRef", "")),
        )
        alt_tag = tags.get("GPS GPSAltitude")
        if alt_tag:
            alt_val = getattr(alt_tag, "values", None)
            if alt_val:
                result.gps_altitude = _ratio_to_float(alt_val[0])
                alt_ref = str(tags.get("GPS GPSAltitudeRef", ""))
                # AltitudeRef 1 = below sea level
                if alt_ref == "1":
                    result.gps_altitude = -result.gps_altitude

        # Camera
        if "Image Make" in tags:
            result.camera_make = str(tags["Image Make"]).strip()
        if "Image Model" in tags:
            result.camera_model = str(tags["Image Model"]).strip()
        if "EXIF LensModel" in tags:
            result.lens_model = str(tags["EXIF LensModel"]).strip()

        # Exposure
        if "EXIF FocalLength" in tags:
            result.focal_length = str(tags["EXIF FocalLength"])
        if "EXIF FNumber" in tags:
            result.aperture = str(tags["EXIF FNumber"])
        if "EXIF ExposureTime" in tags:
            result.exposure_time = str(tags["EXIF ExposureTime"])
        if "EXIF ISOSpeedRatings" in tags:
            try:
                result.iso = int(str(tags["EXIF ISOSpeedRatings"]))
            except ValueError:
                pass
        if "Image Orientation" in tags:
            try:
                result.orientation = int(str(tags["Image Orientation"]))
            except ValueError:
                pass

    except Exception as exc:
        logger.warning("Failed to extract EXIF from %s: %s", path, exc)
    return result


def _image_size(path: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Failed to read image size for %s: %s", path, exc)
        return None, None


def _is_writable_directory(path: Path) -> bool:
    """Best-effort check whether a directory is writable by this process."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except (OSError, PermissionError):
        return False


def _scan_worker_count() -> int:
    return max(1, int(getattr(settings, "scan_thumbnail_concurrency", 4) or 4))


def _scan_queue_limit() -> int:
    queue_limit = max(1, int(getattr(settings, "scan_queue_max_size", 200) or 200))
    return max(queue_limit, _scan_worker_count())


def _scan_db_batch_size() -> int:
    return max(1, int(getattr(settings, "scan_db_write_batch_size", 20) or 20))


def _scan_retry_limit() -> int:
    return max(1, int(getattr(settings, "scan_task_retry_limit", 3) or 3))


def _load_existing_photo_index(db: Session, project_id: int) -> dict[str, ExistingPhotoSnapshot]:
    rows = (
        db.query(
            Photo.file_path,
            Photo.file_hash,
            Photo.thumbnail_path,
            Photo.relative_path,
            Photo.folder_path,
        )
        .filter(
            Photo.project_id == project_id,
            Photo.deleted_at.is_(None),
        )
        .all()
    )
    return {
        file_path: ExistingPhotoSnapshot(
            file_hash=file_hash,
            thumbnail_path=thumbnail_path,
            relative_path=relative_path,
            folder_path=folder_path,
        )
        for file_path, file_hash, thumbnail_path, relative_path, folder_path in rows
    }


def _is_permanent_scan_error(exc: Exception) -> bool:
    return isinstance(exc, (FileNotFoundError, IsADirectoryError, UnidentifiedImageError, ValueError))


def _prepare_scan_file(
    file_path: Path,
    *,
    project_id: int,
    thumbnail_root: str,
    relative_base_path: Optional[str],
    existing: Optional[ExistingPhotoSnapshot],
) -> PreparedScanFile:
    started_at = perf_counter()
    path_str = str(file_path)
    stat = file_path.stat()

    relative_path = None
    folder_path = None
    if relative_base_path:
        relative_path, folder_path = build_relative_paths(relative_base_path, file_path)

    file_hash = _compute_hash(path_str)
    if existing and existing.file_hash == file_hash:
        thumbnail_path = existing.thumbnail_path
        if not thumbnail_path or not Path(thumbnail_path).exists():
            thumbnail_path = generate_thumbnail(
                path_str,
                thumbnail_root=thumbnail_root,
                project_id=project_id,
            )
        return PreparedScanFile(
            path=file_path,
            path_str=path_str,
            relative_path=relative_path,
            folder_path=folder_path,
            file_hash=file_hash,
            file_size=stat.st_size,
            mime_type=None,
            width=None,
            height=None,
            exif=StructuredExif(),
            thumbnail_path=thumbnail_path,
            action="refresh",
            latency_ms=int((perf_counter() - started_at) * 1000),
        )

    mime_type, _ = mimetypes.guess_type(path_str)
    if mime_type is None:
        suffix = file_path.suffix.lower()
        if suffix in (".heic", ".heif"):
            mime_type = "image/heic"
    width, height = _image_size(path_str)
    exif = _extract_exif(path_str)
    thumbnail_path = generate_thumbnail(
        path_str,
        force=True,
        thumbnail_root=thumbnail_root,
        project_id=project_id,
    )
    return PreparedScanFile(
        path=file_path,
        path_str=path_str,
        relative_path=relative_path,
        folder_path=folder_path,
        file_hash=file_hash,
        file_size=stat.st_size,
        mime_type=mime_type,
        width=width,
        height=height,
        exif=exif,
        thumbnail_path=thumbnail_path,
        action="upsert",
        latency_ms=int((perf_counter() - started_at) * 1000),
    )


def _prepare_scan_file_with_retries(
    file_path: Path,
    *,
    project_id: int,
    thumbnail_root: str,
    relative_base_path: Optional[str],
    existing: Optional[ExistingPhotoSnapshot],
) -> PreparedScanFile:
    retry_limit = _scan_retry_limit()
    last_error: Optional[Exception] = None
    for attempt in range(1, retry_limit + 1):
        try:
            return _prepare_scan_file(
                file_path,
                project_id=project_id,
                thumbnail_root=thumbnail_root,
                relative_base_path=relative_base_path,
                existing=existing,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if _is_permanent_scan_error(exc) or attempt >= retry_limit:
                raise
            logger.warning(
                "scan_prepare_retry project_id=%s path=%s attempt=%s/%s error=%s",
                project_id,
                file_path,
                attempt,
                retry_limit,
                exc,
            )
    assert last_error is not None
    raise last_error


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _persist_prepared_file(
    db: Session,
    prepared: PreparedScanFile,
    state: dict[str, Any],
    project_id: int,
) -> None:
    """Persist one prepared image file within the scope of a specific project.

    All reads and writes are strictly scoped to `project_id`.
    The same physical file path in two different projects results in two
    independent Photo rows — no cross-project ownership transfer.
    """
    path_str = prepared.path_str

    # Compute project-relative folder info.
    relative_path = prepared.relative_path
    folder_path = prepared.folder_path
    folder_id = None
    if folder_path is not None:
        folder_cache = state.setdefault("_folder_cache", {})
        folder = ensure_folder_path(db, project_id, folder_path, folder_cache)
        folder_id = folder.id

    # Scope the lookup to this project — the same path is allowed in multiple
    # projects; we must never touch a row owned by a different project.
    existing: Optional[Photo] = (
        db.query(Photo)
        .filter(
            Photo.project_id == project_id,
            Photo.file_path == path_str,
            Photo.deleted_at.is_(None),
        )
        .first()
    )
    if prepared.action == "refresh":
        if existing is None:
            raise RuntimeError(f"Photo disappeared during scan persistence: {path_str}")
        _mark_persisted(state, path=path_str, latency_ms=prepared.latency_ms)
        dirty = False
        if prepared.thumbnail_path and existing.thumbnail_path != prepared.thumbnail_path:
            existing.thumbnail_path = prepared.thumbnail_path
            dirty = True
        # Update folder fields if stale (e.g. file was moved within the library).
        if folder_id and (
            existing.folder_id != folder_id
            or existing.relative_path != relative_path
            or existing.folder_path != folder_path
        ):
            existing.folder_id = folder_id
            existing.relative_path = relative_path
            existing.folder_path = folder_path
            dirty = True
        if resolve_photo_location(db, existing):
            dirty = True
        if dirty:
            existing.updated_at = datetime.now()
            state["updated"] += 1
        _push_file_progress(state, path=path_str, status="success")
        logger.debug(
            "scan_file_persisted project_id=%s path=%s action=%s latency_ms=%s",
            project_id,
            path_str,
            prepared.action,
            prepared.latency_ms,
        )
        return

    common_fields: dict[str, Any] = {
        "file_hash": prepared.file_hash,
        "file_size": prepared.file_size,
        "mime_type": prepared.mime_type,
        "width": prepared.width,
        "height": prepared.height,
        "taken_at": prepared.exif.taken_at,
        "exif": prepared.exif.raw,
        "gps_latitude": prepared.exif.gps_latitude,
        "gps_longitude": prepared.exif.gps_longitude,
        "gps_altitude": prepared.exif.gps_altitude,
        "camera_make": prepared.exif.camera_make,
        "camera_model": prepared.exif.camera_model,
        "lens_model": prepared.exif.lens_model,
        "focal_length": prepared.exif.focal_length,
        "aperture": prepared.exif.aperture,
        "exposure_time": prepared.exif.exposure_time,
        "iso": prepared.exif.iso,
        "orientation": prepared.exif.orientation,
        "thumbnail_path": prepared.thumbnail_path,
    }

    if existing:
        _mark_persisted(state, path=path_str, latency_ms=prepared.latency_ms)
        for k, v in common_fields.items():
            setattr(existing, k, v)
        if folder_id:
            existing.folder_id = folder_id
            existing.relative_path = relative_path
            existing.folder_path = folder_path
        resolve_photo_location(db, existing, force=True)
        existing.updated_at = datetime.now()
        state["updated"] += 1
    else:
        _mark_persisted(state, path=path_str, latency_ms=prepared.latency_ms)
        photo = Photo(
            file_path=path_str,
            file_name=prepared.path.name,
            status="pending",
            project_id=project_id,
            folder_id=folder_id,
            relative_path=relative_path,
            folder_path=folder_path,
            **common_fields,
        )
        db.add(photo)
        db.flush()
        resolve_photo_location(db, photo, force=True)
        state["inserted"] += 1

    _push_file_progress(state, path=path_str, status="success")
    logger.debug(
        "scan_file_persisted project_id=%s path=%s action=%s latency_ms=%s",
        project_id,
        path_str,
        prepared.action,
        prepared.latency_ms,
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def scan_project(
    db: Session,
    project_id: int,
    *,
    progress_callback: Optional[ScanProgressCallback] = None,
) -> dict[str, Any]:
    """
    Scan photos for a specific project using its photo_library_path.
    Updates per-project scan state. Designed to be run in a background thread.
    """
    from ..models.project import Project

    state = _empty_state()

    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        state.update(running=False, message=f"Project {project_id} not found")
        logger.error("scan_project: project %d not found", project_id)
        _emit_progress(state, progress_callback)
        return _snapshot_state(state)

    state.update(
        running=True,
        scanned=0,
        discovered_count=0,
        prepared_count=0,
        persisted_count=0,
        inserted=0,
        updated=0,
        errors=0,
        current_stage="discovery",
        current_path=None,
        queue_depth=0,
        last_stage_latency_ms=None,
        message="scanning",
        recent_errors=[],
        recent_files=[],
    )
    _emit_progress(state, progress_callback)

    library = Path(project.photo_library_path)

    if not library.exists():
        state.update(running=False, message=f"Directory not found: {library}", errors=1)
        _push_scan_error(state, f"Directory not found: {library}")
        logger.error("Project library path does not exist: %s", library)
        _emit_progress(state, progress_callback)
        return _snapshot_state(state)

    thumb_path = (project.thumbnail_path or "").strip()
    if not thumb_path:
        state.update(running=False, message="Missing required project thumbnail_path", errors=1)
        _push_scan_error(state, "Missing required project thumbnail_path")
        logger.error("Project %d scan aborted: missing thumbnail_path", project_id)
        _emit_progress(state, progress_callback)
        return _snapshot_state(state)

    thumb_root = Path(thumb_path).resolve()
    if not _is_writable_directory(thumb_root):
        state.update(running=False, message=f"Thumbnail path is not writable: {thumb_root}", errors=1)
        _push_scan_error(state, f"Thumbnail path is not writable: {thumb_root}")
        logger.error("Project %d scan aborted: thumbnail path not writable: %s", project_id, thumb_root)
        _emit_progress(state, progress_callback)
        return _snapshot_state(state)

    existing_index = _load_existing_photo_index(db, project_id)
    pending_writes = 0
    commit_count = 0
    final_message = "done"
    scan_batch_size = _scan_db_batch_size()
    executor = ThreadPoolExecutor(max_workers=_scan_worker_count())
    futures: dict[Future[PreparedScanFile], Path] = {}
    aborted = False
    try:
        def drain_completed(*, wait_for_all: bool = False) -> None:
            nonlocal pending_writes, commit_count
            if not futures:
                return
            done, _ = wait(
                tuple(futures.keys()),
                return_when=ALL_COMPLETED if wait_for_all else FIRST_COMPLETED,
            )
            for future in done:
                entry = futures.pop(future)
                _set_scan_stage(
                    state,
                    stage="prepare",
                    current_path=str(entry),
                    queue_depth=len(futures),
                )
                try:
                    prepared = future.result()
                    state["prepared_count"] = int(state.get("prepared_count") or 0) + 1
                    _persist_prepared_file(db, prepared, state, project_id)
                    state["persisted_count"] = int(state.get("persisted_count") or 0) + 1
                    pending_writes += 1
                    if pending_writes >= scan_batch_size:
                        db.commit()
                        commit_count += 1
                        pending_writes = 0
                except Exception as exc:
                    logger.error("Failed to process %s: %s", entry, exc)
                    db.rollback()
                    state["errors"] += 1
                    _push_scan_error(state, f"{entry.name}: {exc}")
                    _push_file_progress(
                        state,
                        path=str(entry),
                        status="failed",
                        message=str(exc),
                    )
                _set_scan_stage(state, stage="persist", queue_depth=len(futures))
                _emit_progress(state, progress_callback)

        for entry in library.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                entry.resolve().relative_to(thumb_root)
                continue
            except ValueError:
                pass

            state["scanned"] += 1
            state["discovered_count"] = int(state.get("discovered_count") or 0) + 1
            _set_scan_stage(
                state,
                stage="discovery",
                current_path=str(entry),
                queue_depth=len(futures),
            )
            futures[
                executor.submit(
                    _prepare_scan_file_with_retries,
                    entry,
                    project_id=project_id,
                    thumbnail_root=str(thumb_root),
                    relative_base_path=str(library),
                    existing=existing_index.get(str(entry)),
                )
            ] = entry
            _set_scan_stage(
                state,
                stage="prepare",
                current_path=str(entry),
                queue_depth=len(futures),
            )
            if len(futures) >= _scan_queue_limit():
                drain_completed()
            elif state["scanned"] % 25 == 0:
                _emit_progress(state, progress_callback)

        drain_completed(wait_for_all=True)
    except BaseException:
        aborted = True
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=aborted)
        try:
            if pending_writes > 0:
                db.commit()
                commit_count += 1

            if not aborted:
                _set_scan_stage(state, stage="cleanup", queue_depth=0)
                cleanup_missing_project_photos(
                    db,
                    project_id=project_id,
                    batch_size=scan_batch_size,
                )

                # 扫描结束后重算文件夹计数（若失败也不能阻塞状态收尾）
                from .folder_service import recompute_project_folder_counts

                recompute_project_folder_counts(db, project_id)
                db.commit()
        except Exception as exc:
            logger.exception(
                "Failed to recompute folder counts after project %d scan: %s",
                project_id,
                exc,
            )
            state["errors"] += 1
            _push_scan_error(state, f"重算文件夹计数失败: {exc}")
            final_message = "done_with_errors"
        finally:
            state.pop("_folder_cache", None)
            state.update(running=False, current_path=None, queue_depth=0)
            if not aborted:
                state.update(current_stage="done", message=final_message)
                _emit_progress(state, progress_callback)

    logger.info(
        "Project %d scan complete — scanned=%d inserted=%d updated=%d errors=%d commits=%d",
        project_id,
        state["scanned"],
        state["inserted"],
        state["updated"],
        state["errors"],
        commit_count,
    )
    return _snapshot_state(state)


# ---------------------------------------------------------------------------
# Reindex — re-extract metadata for existing DB records
# ---------------------------------------------------------------------------

def reindex_project(
    db: Session,
    project_id: int,
    scope: str = "missing_metadata",
    *,
    progress_callback: Optional[ScanProgressCallback] = None,
) -> dict[str, Any]:
    """Re-extract EXIF metadata (date, GPS, camera info) for photos already in
    the DB without re-traversing the filesystem.

    scope:
      "missing_metadata" — only photos where taken_at IS NULL
      "missing_location" — only photos with GPS but no resolved place fields
      "all"              — every photo belonging to this project

    Returns a ScanStatus-compatible payload and can stream progress through
    *progress_callback* for persisted task updates.
    """
    state = _empty_state()

    query = db.query(Photo).filter(
        Photo.project_id == project_id,
        Photo.deleted_at.is_(None),
    )
    if scope == "missing_metadata":
        query = query.filter(Photo.taken_at.is_(None))
    elif scope == "missing_location":
        query = query.filter(
            Photo.gps_latitude.is_not(None),
            Photo.gps_longitude.is_not(None),
            Photo.location_resolved_at.is_(None),
        )

    photos: list[Photo] = query.all()

    state.update(
        running=True,
        scanned=0,
        inserted=0,
        updated=0,
        errors=0,
        current_path=None,
        message=f"reindexing ({scope})",
        recent_errors=[],
        recent_files=[],
    )
    _emit_progress(state, progress_callback)

    try:
        for photo in photos:
            state["current_path"] = photo.file_path
            state["scanned"] += 1
            if state["scanned"] % 10 == 0:
                _emit_progress(state, progress_callback)

            if not Path(photo.file_path).exists():
                warning = f"photo#{photo.id} 文件不存在: {photo.file_path}"
                logger.warning("reindex: %s", warning)
                _push_scan_error(state, warning)
                _push_file_progress(
                    state,
                    path=photo.file_path,
                    status="failed",
                    message=warning,
                )
                _emit_progress(state, progress_callback)
                continue

            try:
                exif = _extract_exif(photo.file_path)
                changed = False

                for attr, value in [
                    ("taken_at", exif.taken_at),
                    ("exif", exif.raw),
                    ("gps_latitude", exif.gps_latitude),
                    ("gps_longitude", exif.gps_longitude),
                    ("gps_altitude", exif.gps_altitude),
                    ("camera_make", exif.camera_make),
                    ("camera_model", exif.camera_model),
                    ("lens_model", exif.lens_model),
                    ("focal_length", exif.focal_length),
                    ("aperture", exif.aperture),
                    ("exposure_time", exif.exposure_time),
                    ("iso", exif.iso),
                    ("orientation", exif.orientation),
                ]:
                    if value is not None and getattr(photo, attr) != value:
                        setattr(photo, attr, value)
                        changed = True

                if resolve_photo_location(db, photo, force=(scope == "all")):
                    changed = True

                if changed:
                    photo.updated_at = datetime.now()
                    db.commit()
                    state["updated"] += 1
                    _push_file_progress(state, path=photo.file_path, status="success")
                    _emit_progress(state, progress_callback)
                else:
                    _push_file_progress(state, path=photo.file_path, status="success")
            except Exception as exc:
                logger.error(
                    "reindex: failed to process photo %d (%s): %s",
                    photo.id,
                    photo.file_path,
                    exc,
                )
                db.rollback()
                state["errors"] += 1
                _push_scan_error(state, f"photo#{photo.id} {Path(photo.file_path).name}: {exc}")
                _push_file_progress(
                    state,
                    path=photo.file_path,
                    status="failed",
                    message=str(exc),
                )
                _emit_progress(state, progress_callback)
    finally:
        state.update(running=False, current_path=None, message="done")
        _emit_progress(state, progress_callback)

    logger.info(
        "Project %d reindex complete — scanned=%d updated=%d errors=%d",
        project_id,
        state["scanned"],
        state["updated"],
        state["errors"],
    )
    return _snapshot_state(state)
