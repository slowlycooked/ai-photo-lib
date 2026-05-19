from __future__ import annotations

import hashlib
from typing import Optional
import logging
from pathlib import Path

import pillow_heif
from PIL import Image

from ..config import settings

# Register HEIF/HEIC opener so PIL.Image.open() handles these formats transparently
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def _thumb_path(file_path: str) -> Path:
    """Derive a stable thumbnail path from the source file path."""
    digest = hashlib.sha1(file_path.encode()).hexdigest()
    sub = digest[:2]
    thumb_dir = Path(settings.thumbnail_path) / sub
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f"{digest}.jpg"


def generate_thumbnail(file_path: str, *, force: bool = False) -> Optional[str]:
    """
    Generate a JPEG thumbnail with the long edge capped at THUMBNAIL_SIZE.
    Returns the thumbnail path on success, None on failure.
    Idempotent by default: skips generation if thumbnail already exists.
    Pass force=True to overwrite an existing (potentially stale) thumbnail.
    """
    thumb_path = _thumb_path(file_path)
    if thumb_path.exists() and not force:
        return str(thumb_path)

    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            max_size = settings.thumbnail_size
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
        return str(thumb_path)
    except Exception as exc:
        suffix = Path(file_path).suffix.lower()
        level = logging.ERROR if suffix in (".heic", ".heif") else logging.WARNING
        logger.log(level, "Thumbnail failed for %s: %s", file_path, exc)
        return None
