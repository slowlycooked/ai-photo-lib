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

# Mutable dict shared between scan thread and API — reads are safe without locks
# because only one scan can run at a time (enforced by the router).
scan_state: dict[str, Any] = {
    "running": False,
    "scanned": 0,
    "inserted": 0,
    "updated": 0,
    "errors": 0,
    "current_path": None,
    "message": "idle",
}


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

def _process_file(db: Session, file_path: Path) -> None:
    path_str = str(file_path)
    stat = file_path.stat()

    existing: Optional[Photo] = db.query(Photo).filter(Photo.file_path == path_str).first()
    # Fast-path: photos in a library are immutable — if size is unchanged and a
    # hash is already stored, skip the expensive hash recomputation entirely.
    if existing and existing.file_size == stat.st_size and existing.file_hash is not None:
        return  # unchanged — nothing to do

    file_hash = _compute_hash(path_str)
    if existing and existing.file_hash == file_hash:
        return  # confirmed unchanged by hash
    mime_type, _ = mimetypes.guess_type(path_str)
    width, height = _image_size(path_str)
    exif_data, taken_at = _extract_exif(path_str)
    thumbnail_path = generate_thumbnail(path_str)

    if existing:
        existing.file_hash = file_hash
        existing.file_size = stat.st_size
        existing.mime_type = mime_type
        existing.width = width
        existing.height = height
        existing.taken_at = taken_at
        existing.exif = exif_data
        existing.thumbnail_path = thumbnail_path
        existing.updated_at = datetime.now()
        db.commit()
        scan_state["updated"] += 1
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
            )
        )
        db.commit()
        scan_state["inserted"] += 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scan_directory(db: Session) -> None:
    """
    Recursively scan PHOTO_LIBRARY_PATH and upsert photo records.
    Designed to be run in a background thread; updates scan_state in place.
    Safe to restart: unchanged files (same hash) are skipped.
    """
    scan_state.update(
        running=True,
        scanned=0,
        inserted=0,
        updated=0,
        errors=0,
        current_path=None,
        message="scanning",
    )

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
                _process_file(db, entry)
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
