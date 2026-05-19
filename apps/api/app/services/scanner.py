from __future__ import annotations

import hashlib
import logging
import mimetypes
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
from .json_parser import build_relative_paths
from .folder_service import ensure_folder_path

logger = logging.getLogger(__name__)

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
    }


# Global state for the legacy /scan/* endpoints (default project)
scan_state: dict[str, Any] = _empty_state()

# Per-project state keyed by project_id
_project_scan_states: dict[int, dict[str, Any]] = {}


def get_project_scan_state(project_id: int) -> dict[str, Any]:
    if project_id not in _project_scan_states:
        _project_scan_states[project_id] = _empty_state()
    return _project_scan_states[project_id]


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
        with open(path, "rb") as fh:
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


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _process_file(
    db: Session,
    file_path: Path,
    state: dict[str, Any],
    project_id: Optional[int] = None,
) -> None:
    path_str = str(file_path)
    stat = file_path.stat()

    # 计算 relative_path 和 folder_path
    relative_path = None
    folder_path = None
    folder_id = None
    if project_id is not None:
        from ..models.project import Project
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            relative_path, folder_path = build_relative_paths(project.photo_library_path, file_path)
            folder_cache = state.setdefault("_folder_cache", {})
            folder = ensure_folder_path(db, project_id, folder_path, folder_cache)
            folder_id = folder.id

    existing: Optional[Photo] = db.query(Photo).filter(Photo.file_path == path_str).first()
    file_hash = _compute_hash(path_str)
    if existing and existing.file_hash == file_hash:
        dirty = False
        if not existing.thumbnail_path or not Path(existing.thumbnail_path).exists():
            new_thumb = generate_thumbnail(path_str)
            if new_thumb:
                existing.thumbnail_path = new_thumb
                dirty = True
        if project_id is not None and existing.project_id is None:
            existing.project_id = project_id
            dirty = True
        # 新增：补齐 folder 字段
        if folder_id and (existing.folder_id != folder_id or existing.relative_path != relative_path or existing.folder_path != folder_path):
            existing.folder_id = folder_id
            existing.relative_path = relative_path
            existing.folder_path = folder_path
            dirty = True
        if dirty:
            existing.updated_at = datetime.now()
            db.commit()
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
    thumbnail_path = generate_thumbnail(path_str, force=True)

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
        if project_id is not None:
            existing.project_id = project_id
        # 新增：补齐 folder 字段
        if folder_id:
            existing.folder_id = folder_id
            existing.relative_path = relative_path
            existing.folder_path = folder_path
        existing.updated_at = datetime.now()
        db.commit()
        state["updated"] += 1
    else:
        db.add(
            Photo(
                file_path=path_str,
                file_name=file_path.name,
                status="pending",
                project_id=project_id,
                folder_id=folder_id,
                relative_path=relative_path,
                folder_path=folder_path,
                **common_fields,
            )
        )
        db.commit()
        state["inserted"] += 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scan_directory(db: Session) -> None:
    """
    Legacy scan using settings.photo_library_path.
    Resolves the default project if available and tags new photos with it.
    Designed to be run in a background thread; updates scan_state in place.
    """
    from ..models.project import Project

    scan_state.update(
        running=True,
        scanned=0,
        inserted=0,
        updated=0,
        errors=0,
        current_path=None,
        message="scanning",
    )

    default_project = (
        db.query(Project)
        .filter(Project.is_default.is_(True), Project.deleted_at.is_(None))
        .first()
    )
    project_id = default_project.id if default_project else None

    library = Path(settings.photo_library_path)
    if not library.exists():
        scan_state.update(running=False, message=f"Directory not found: {library}")
        logger.error("Photo library path does not exist: %s", library)
        return

    # Resolve thumbnail root once so we can skip it during rglob
    thumb_root = Path(settings.thumbnail_path).resolve()

    try:
        for entry in library.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            # Skip generated thumbnails (they live inside PHOTO_LIBRARY_PATH)
            try:
                entry.resolve().relative_to(thumb_root)
                continue  # inside thumbnail directory — not an original photo
            except ValueError:
                pass  # outside thumbnail directory — proceed

            scan_state["current_path"] = str(entry)
            scan_state["scanned"] += 1

            try:
                _process_file(db, entry, scan_state, project_id)
            except Exception as exc:
                logger.error("Failed to process %s: %s", entry, exc)
                scan_state["errors"] += 1
    finally:
        final_message = "done"
        try:
            # 扫描结束后重算文件夹计数（若失败也不能阻塞状态收尾）
            from .folder_service import recompute_project_folder_counts
            from ..models.project import Project

            # 重新计算所有项目的文件夹计数，确保数据一致性
            all_projects = db.query(Project).filter(Project.deleted_at.is_(None)).all()
            for proj in all_projects:
                try:
                    recompute_project_folder_counts(db, proj.id)
                except Exception as e:
                    logger.warning("Failed to recompute folder counts for project %d: %s", proj.id, e)
            
            db.commit()
        except Exception as exc:
            logger.exception("Failed to recompute folder counts after scan: %s", exc)
            scan_state["errors"] += 1
            final_message = "done_with_errors"
        finally:
            scan_state.pop("_folder_cache", None)
            scan_state.update(running=False, current_path=None, message=final_message)

        logger.info(
            "Scan complete — scanned=%d inserted=%d updated=%d errors=%d",
            scan_state["scanned"],
            scan_state["inserted"],
            scan_state["updated"],
            scan_state["errors"],
        )


def scan_project(db: Session, project_id: int) -> None:
    """
    Scan photos for a specific project using its photo_library_path.
    Updates per-project scan state. Designed to be run in a background thread.
    """
    from ..models.project import Project

    state = get_project_scan_state(project_id)

    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.deleted_at.is_(None))
        .first()
    )
    if not project:
        state.update(running=False, message=f"Project {project_id} not found")
        logger.error("scan_project: project %d not found", project_id)
        return

    state.update(
        running=True,
        scanned=0,
        inserted=0,
        updated=0,
        errors=0,
        current_path=None,
        message="scanning",
    )

    library = Path(project.photo_library_path)
    if not library.exists():
        state.update(running=False, message=f"Directory not found: {library}")
        logger.error("Project library path does not exist: %s", library)
        return

    thumb_path = project.thumbnail_path or settings.thumbnail_path
    thumb_root = Path(thumb_path).resolve()

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

            try:
                _process_file(db, entry, state, project_id)
            except Exception as exc:
                logger.error("Failed to process %s: %s", entry, exc)
                state["errors"] += 1
    finally:
        final_message = "done"
        try:
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
            final_message = "done_with_errors"
        finally:
            state.pop("_folder_cache", None)
            state.update(running=False, current_path=None, message=final_message)

        logger.info(
            "Project %d scan complete — scanned=%d inserted=%d updated=%d errors=%d",
            project_id,
            state["scanned"],
            state["inserted"],
            state["updated"],
            state["errors"],
        )
