"""Image decode service — unified entry point for reading photo files.

Responsibilities:
- Detect file format (JPEG, PNG, WebP, HEIC/HEIF, …)
- Decode HEIC/HEIF via pillow-heif
- Apply EXIF orientation correction
- Normalize to sRGB
- Return a PIL Image *or* a NumPy BGR array ready for OpenCV

All callers that need pixel data should go through this service rather than
calling ``cv2.imread`` or ``Image.open`` directly, so that HEIC support and
orientation fixes are applied consistently.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import numpy as np
import pillow_heif
from PIL import Image, ImageOps

# Register the HEIF/HEIC opener once at import time so that
# PIL.Image.open() handles these formats transparently everywhere.
pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

# File suffixes considered HEIC/HEIF (lower-case, with leading dot)
_HEIC_SUFFIXES = frozenset({".heic", ".heif"})


def read_image_pil(path: Union[str, Path]) -> Image.Image:
    """Read an image file and return a PIL Image in RGB mode.

    Handles:
    - HEIC/HEIF via pillow-heif (including Display P3 / HDR tone-mapping)
    - EXIF orientation correction for all formats
    - Converts to RGB (removes alpha channel, handles palette images)

    Raises
    ------
    FileNotFoundError
        When the file does not exist on disk.
    OSError
        When the file cannot be decoded (e.g. corrupted or unsupported format).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    with Image.open(p) as img:
        # Apply EXIF orientation before any other processing.
        # ImageOps.exif_transpose() is safe on images without EXIF.
        img = ImageOps.exif_transpose(img)
        # Normalise colour mode — convert palette/grayscale/RGBA → RGB.
        if img.mode != "RGB":
            img = img.convert("RGB")
        # Return a *copy* so the with-block can safely close the file handle.
        return img.copy()


def read_image_bgr(path: Union[str, Path]) -> np.ndarray:
    """Read an image file and return an OpenCV-compatible BGR NumPy array.

    This is the recommended way to feed images into OpenCV-based face
    detection / embedding pipelines, replacing direct ``cv2.imread()`` calls.

    The returned array has dtype ``uint8`` and shape ``(H, W, 3)``.

    Raises
    ------
    FileNotFoundError
        When the file does not exist on disk.
    OSError
        When the file cannot be decoded.
    """
    img_rgb = read_image_pil(path)
    img_rgb_arr = np.array(img_rgb, dtype=np.uint8)
    # PIL/NumPy array is RGB; OpenCV expects BGR.
    img_bgr = img_rgb_arr[:, :, ::-1].copy()
    return img_bgr
