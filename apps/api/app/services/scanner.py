from __future__ import annotations

import hashlib
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import exifread
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from ..config import settings
from ..models.photo import Photo
from .thumbnail import SUPPORTED_SUFFIXES, generate_thumbnail

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


def _extract_exif(path: str) -> Tuple[Optional[Dict], Optional[datetime]]:
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, stop_tag="UNDEF", details=False)
        if not tags:
            return None, None
        safe = {k: str(v) for k, v in tags.items() if not k.startswith("Thumbnail")}
        return safe, _parse_exif_dt(tags)
    except Exception:
        return None, None


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
    exif_data, taken_at = _extract_exif(path_str)
    # File content has changed (hash differs) — force thumbnail regeneration so
    # the displayed thumbnail always matches the current file on disk.
    thumbnail_path = generate_thumbnail(path_str, force=True)

    if existing:
        existing.file_hash = file_hash
        existing.file_size = stat.st_size
        existing.mime_type = mime_type
        existing.width = width
        existing.height = height
        existing.taken_at = taken_at
        existing.exif = exif_data
        existing.thumbnail_path = thumbnail_path
        if project_id is not None:
            existing.project_id = project_id
        existing.updated_at = datetime.now()
        db.commit()
        state["updated"] += 1
    else:
        db.add(
            Photo(
                file_path=path_str,
                file_name=file_path.name,
                file_hash=file_hash,
                file_size=stat.st_size,
                mime_type=mime_type,
                width=width,
                height=height,
                taken_at=taken_at,
                exif=exif_data,
                thumbnail_path=thumbnail_path,
                status="pending",
                project_id=project_id,
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
        scan_state.update(running=False, current_path=None, message="done")
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
        state.update(running=False, current_path=None, message="done")
        logger.info(
            "Project %d scan complete — scanned=%d inserted=%d updated=%d errors=%d",
            project_id,
            state["scanned"],
            state["inserted"],
            state["updated"],
            state["errors"],
        )
