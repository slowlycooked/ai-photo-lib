from __future__ import annotations

import hashlib
from typing import Optional
import logging
from pathlib import Path

from PIL import Image

from ..config import settings

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def _thumb_path(file_path: str) -> Path:
    """Derive a stable thumbnail path from the source file path."""
    digest = hashlib.sha1(file_path.encode()).hexdigest()
    sub = digest[:2]
    thumb_dir = Path(settings.thumbnail_path) / sub
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f"{digest}.webp"


def generate_thumbnail(file_path: str) -> Optional[str]:
    """
    Generate a WebP thumbnail with the long edge capped at THUMBNAIL_SIZE.
    Returns the thumbnail path on success, None on failure.
    Idempotent: skips generation if thumbnail already exists.
    """
    thumb_path = _thumb_path(file_path)
    if thumb_path.exists():
        return str(thumb_path)

    try:
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            max_size = settings.thumbnail_size
            img.thumbnail((max_size, max_size), Image.LANCZOS)
            img.save(thumb_path, "WEBP", quality=82, optimize=True)
        return str(thumb_path)
    except Exception as exc:
        logger.warning("Thumbnail failed for %s: %s", file_path, exc)
        return None
