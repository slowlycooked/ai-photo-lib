from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

import cv2
from PIL import Image

from ..config import settings
from .image_decode_service import read_image_pil

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES


class ThumbnailGenerationError(RuntimeError):
    """Raised when thumbnail generation fails and the caller needs the cause."""

    def __init__(self, file_path: str, cause: Exception) -> None:
        super().__init__(f"Thumbnail generation failed for {file_path}: {cause}")
        self.file_path = file_path
        self.cause = cause


def _thumb_path(
    file_path: str,
    *,
    project_id: Optional[int] = None,
    thumbnail_root: Optional[str] = None,
) -> Path:
    """Derive a stable thumbnail path from the source file path.

    When ``project_id`` is supplied the hash key includes it, so the same
    physical file can be thumbnailed independently per project.  When
    ``thumbnail_root`` is supplied it overrides the global setting, allowing
    per-project thumbnail directories.
    """
    hash_key = f"{project_id}:{file_path}" if project_id is not None else file_path
    digest = hashlib.sha1(hash_key.encode()).hexdigest()
    sub = digest[:2]
    root = Path(thumbnail_root) if thumbnail_root else Path(settings.thumbnail_path)
    thumb_dir = root / sub
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f"{digest}.jpg"


def generate_thumbnail(
    file_path: str,
    *,
    force: bool = False,
    project_id: Optional[int] = None,
    thumbnail_root: Optional[str] = None,
    raise_on_error: bool = False,
) -> Optional[str]:
    """
    Generate a JPEG thumbnail with the long edge capped at THUMBNAIL_SIZE.
    Returns the thumbnail path on success, None on failure.
    Idempotent by default: skips generation if thumbnail already exists.
    Pass force=True to overwrite an existing (potentially stale) thumbnail.

    ``project_id`` is incorporated into the hash key so that two projects
    sharing the same physical file get independent thumbnail entries.
    ``thumbnail_root`` overrides the global thumbnail directory, allowing
    per-project thumbnail isolation.
    """
    thumb_path = _thumb_path(
        file_path,
        project_id=project_id,
        thumbnail_root=thumbnail_root,
    )
    if thumb_path.exists() and not force:
        return str(thumb_path)

    try:
        suffix = Path(file_path).suffix.lower()
        if suffix in VIDEO_SUFFIXES:
            capture = cv2.VideoCapture(file_path)
            try:
                if not capture.isOpened():
                    raise OSError("video decoder could not open the file")
                frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                if frame_count > 1:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_count * 0.1)))
                ok, frame = capture.read()
                if not ok or frame is None:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = capture.read()
                if not ok or frame is None:
                    raise OSError("video decoder could not read a preview frame")
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            finally:
                capture.release()
        else:
            img = read_image_pil(file_path)
        try:
            max_size = settings.thumbnail_size
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
        finally:
            img.close()
        return str(thumb_path)
    except Exception as exc:
        level = logging.ERROR if suffix in (".heic", ".heif") else logging.WARNING
        logger.log(level, "Thumbnail failed for %s: %s", file_path, exc, exc_info=True)
        if raise_on_error:
            raise ThumbnailGenerationError(file_path, exc) from exc
        return None
