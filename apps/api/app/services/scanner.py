from __future__ import annotations

import hashlib
import io
import logging
import mimetypes
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
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

# Commit scan writes in batches to reduce transaction overhead on large libraries.
_SCAN_COMMIT_BATCH_SIZE = 100

ScanProgressCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Scan state management
# ---------------------------------------------------------------------------

def _empty_state() -> dict[str, Any]:
    return {
        "running": False,
        "scanned": 0,
        "inserted": 0,
        "updated": 0,
        "errors": 0,
        "current_path": None,
        "message": "idle",
        "recent_errors": [],
    }


def _push_scan_error(state: dict[str, Any], message: str, *, limit: int = 20) -> None:
    errors = state.setdefault("recent_errors", [])
    errors.append(message)
    if len(errors) > limit:
        del errors[:-limit]


def _snapshot_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "running": bool(state.get("running")),
        "scanned": int(state.get("scanned") or 0),
        "inserted": int(state.get("inserted") or 0),
        "updated": int(state.get("updated") or 0),
        "errors": int(state.get("errors") or 0),
        "current_path": state.get("current_path"),
        "message": str(state.get("message") or "idle"),
        "recent_errors": list(state.get("recent_errors") or []),
    }


def _emit_progress(
    state: dict[str, Any],
    progress_callback: Optional[ScanProgressCallback],
) -> None:
    if progress_callback is not None:
        progress_callback(_snapshot_state(state))


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

    except Exception:
        pass
    return result


def _image_size(path: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except (UnidentifiedImageError, Exception):
        return None, None


def _is_writable_directory(path: Path) -> bool:
    """Best-effort check whether a directory is writable by this process."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process_file(
    db: Session,
    file_path: Path,
    state: dict[str, Any],
    project_id: int,
    thumbnail_root: Optional[str] = None,
    relative_base_path: Optional[str] = None,
) -> None:
    """Process one image file within the scope of a specific project.

    All reads and writes are strictly scoped to `project_id`.
    The same physical file path in two different projects results in two
    independent Photo rows — no cross-project ownership transfer.
    """
    path_str = str(file_path)
    stat = file_path.stat()

    # Compute project-relative folder info.
    relative_path = None
    folder_path = None
    folder_id = None
    if relative_base_path:
        relative_path, folder_path = build_relative_paths(relative_base_path, file_path)
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
    file_hash = _compute_hash(path_str)
    if existing and existing.file_hash == file_hash:
        dirty = False
        if not existing.thumbnail_path or not Path(existing.thumbnail_path).exists():
            new_thumb = generate_thumbnail(path_str, thumbnail_root=thumbnail_root, project_id=project_id)
            if new_thumb:
                existing.thumbnail_path = new_thumb
                dirty = True
        # Update folder fields if stale (e.g. file was moved within the library).
        if folder_id and (existing.folder_id != folder_id or existing.relative_path != relative_path or existing.folder_path != folder_path):
            existing.folder_id = folder_id
            existing.relative_path = relative_path
            existing.folder_path = folder_path
            dirty = True
        if resolve_photo_location(db, existing):
            dirty = True
        if dirty:
            existing.updated_at = datetime.now()
            state["updated"] += 1
        return

    mime_type, _ = mimetypes.guess_type(path_str)
    # mimetypes may not know HEIC/HEIF on all platforms
    if mime_type is None:
        suffix = file_path.suffix.lower()
        if suffix in (".heic", ".heif"):
            mime_type = "image/heic"
    width, height = _image_size(path_str)
    exif = _extract_exif(path_str)
    # File content has changed (hash differs) — force thumbnail regeneration so
    # the displayed thumbnail always matches the current file on disk.
    thumbnail_path = generate_thumbnail(path_str, force=True, thumbnail_root=thumbnail_root, project_id=project_id)

    common_fields: dict[str, Any] = {
        "file_hash": file_hash,
        "file_size": stat.st_size,
        "mime_type": mime_type,
        "width": width,
        "height": height,
        "taken_at": exif.taken_at,
        "exif": exif.raw,
        "gps_latitude": exif.gps_latitude,
        "gps_longitude": exif.gps_longitude,
        "gps_altitude": exif.gps_altitude,
        "camera_make": exif.camera_make,
        "camera_model": exif.camera_model,
        "lens_model": exif.lens_model,
        "focal_length": exif.focal_length,
        "aperture": exif.aperture,
        "exposure_time": exif.exposure_time,
        "iso": exif.iso,
        "orientation": exif.orientation,
        "thumbnail_path": thumbnail_path,
    }

    if existing:
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
        photo = Photo(
            file_path=path_str,
            file_name=file_path.name,
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
        inserted=0,
        updated=0,
        errors=0,
        current_path=None,
        message="scanning",
        recent_errors=[],
    )
    _emit_progress(state, progress_callback)

    library = Path(project.photo_library_path)
    resolved_library = False
    if not library.exists() and project.is_default:
        # Compatibility fallback for older records that still store `/photos`
        # while the native runtime is configured with a host path.
        configured_default = Path(settings.photo_library_path)
        if configured_default.exists():
            logger.warning(
                "Project %d library path %s not found; fallback to settings.photo_library_path=%s",
                project_id,
                library,
                configured_default,
            )
            library = configured_default
            resolved_library = True

    if not library.exists() and project.is_default:
        configured_host = Path(settings.host_photo_library_path)
        if configured_host.exists():
            logger.warning(
                "Project %d library path %s not found; fallback to settings.host_photo_library_path=%s",
                project_id,
                library,
                configured_host,
            )
            library = configured_host
            resolved_library = True

    if resolved_library and str(library) != project.photo_library_path:
        # Persist the resolved path so future scans do not rely on fallback.
        project.photo_library_path = str(library)
        project.updated_at = datetime.now()
        db.commit()

    if not library.exists():
        state.update(running=False, message=f"Directory not found: {library}")
        logger.error("Project library path does not exist: %s", library)
        _emit_progress(state, progress_callback)
        return _snapshot_state(state)

    thumb_path = project.thumbnail_path or settings.thumbnail_path
    thumb_root = Path(thumb_path).resolve()
    if project.is_default and not _is_writable_directory(thumb_root):
        configured_thumb = Path(settings.thumbnail_path).resolve()
        if _is_writable_directory(configured_thumb):
            logger.warning(
                "Project %d thumbnail path %s is not writable; fallback to settings.thumbnail_path=%s",
                project_id,
                thumb_root,
                configured_thumb,
            )
            thumb_root = configured_thumb
            if str(configured_thumb) != (project.thumbnail_path or ""):
                project.thumbnail_path = str(configured_thumb)
                project.updated_at = datetime.now()
                db.commit()

    pending_writes = 0
    commit_count = 0
    final_message = "done"
    try:
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

            state["current_path"] = str(entry)
            state["scanned"] += 1
            if state["scanned"] % 25 == 0:
                _emit_progress(state, progress_callback)

            try:
                _process_file(
                    db,
                    entry,
                    state,
                    project_id,
                    thumbnail_root=str(thumb_root),
                    relative_base_path=str(library),
                )
                pending_writes += 1
                if pending_writes >= _SCAN_COMMIT_BATCH_SIZE:
                    db.commit()
                    commit_count += 1
                    pending_writes = 0
                    _emit_progress(state, progress_callback)
            except Exception as exc:
                logger.error("Failed to process %s: %s", entry, exc)
                db.rollback()
                state["errors"] += 1
                _push_scan_error(state, f"{entry.name}: {exc}")
                _emit_progress(state, progress_callback)
    finally:
        try:
            if pending_writes > 0:
                db.commit()
                commit_count += 1

            cleanup_missing_project_photos(
                db,
                project_id=project_id,
                batch_size=_SCAN_COMMIT_BATCH_SIZE,
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
            state.update(running=False, current_path=None, message=final_message)
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
                    _emit_progress(state, progress_callback)
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
