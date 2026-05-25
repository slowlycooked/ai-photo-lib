"""Derivative image service — generate and cache derived images from source photos.

Three derivative kinds are managed here:

``ai_thumbnail``
    Small JPEG used for AI analysis (VLM) and photo wall display.
    Long-edge capped at ``settings.ai_thumbnail_max_edge`` (default 768 px).

``face_work_image``
    Medium-high resolution JPEG used as the input for face detection.
    Long-edge capped at ``settings.face_work_image_max_edge`` (default 2048 px),
    with a minimum of ``settings.face_work_image_min_edge`` (default 1280 px).
    Written at JPEG quality ``settings.face_work_image_jpeg_quality`` (default 94).

``face_crop``
    Tightly cropped, aligned face region for embedding generation and
    human-confirmation UI.  Created from the face_work_image (or the original
    photo as fallback) using bounding-box + landmark coordinates supplied by
    the caller.

Cache invalidation:
    A derivative is considered stale when the source file mtime or content hash
    changes.  Re-generation is triggered automatically by ``get_or_create``.

Storage layout::

    <derivative_root>/
        projects/<project_id>/
            ai_thumb/<sha1[:2]>/<sha1>.jpg
            face_work/<sha1[:2]>/<sha1>.jpg
            face_crops/<sha1[:2]>/<sha1>.jpg

The ``derivative_root`` defaults to ``<thumbnail_path>/../derivatives`` so that
it lives alongside the existing thumbnail cache and can be Docker-volume-mounted
in the same way.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.derivative import PhotoDerivative
from ..models.face import FaceDetection
from ..models.photo import Photo
from .image_decode_service import read_image_pil

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kind constants
# ---------------------------------------------------------------------------
KIND_AI_THUMBNAIL = "ai_thumbnail"
KIND_FACE_WORK_IMAGE = "face_work_image"
KIND_FACE_CROP = "face_crop"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derivative_root(thumbnail_path: str) -> Path:
    """Resolve the root directory for derivative cache from the thumbnail path."""
    return Path(thumbnail_path).parent / "derivatives"


def _stable_path(
    root: Path,
    project_id: int,
    photo_id: int,
    kind: str,
    ext: str = ".jpg",
) -> Path:
    """Derive a stable, sharded file path for a derivative.

    The key includes project_id and photo_id so derivatives are naturally
    project-isolated even if the underlying file paths happen to collide.
    """
    key = f"{project_id}:{photo_id}:{kind}"
    digest = hashlib.sha1(key.encode()).hexdigest()
    sub = digest[:2]
    kind_dir = root / "projects" / str(project_id) / _kind_subdir(kind) / sub
    kind_dir.mkdir(parents=True, exist_ok=True)
    return kind_dir / f"{digest}{ext}"


def _stable_crop_path(
    root: Path,
    project_id: int,
    face_detection_id: int,
) -> Path:
    key = f"{project_id}:face_crop:{face_detection_id}"
    digest = hashlib.sha1(key.encode()).hexdigest()
    sub = digest[:2]
    crop_dir = root / "projects" / str(project_id) / "face_crops" / sub
    crop_dir.mkdir(parents=True, exist_ok=True)
    return crop_dir / f"{digest}.jpg"


def _kind_subdir(kind: str) -> str:
    return {
        KIND_AI_THUMBNAIL: "ai_thumb",
        KIND_FACE_WORK_IMAGE: "face_work",
        KIND_FACE_CROP: "face_crops",
    }.get(kind, kind)


def _source_mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _is_stale(record: PhotoDerivative, source_path: str) -> bool:
    """Return True when the cached derivative should be regenerated."""
    # File no longer on disk → stale
    if not record.path or not Path(record.path).exists():
        return True
    # Source moved/deleted → stale
    if not Path(source_path).exists():
        return True
    current_mtime = _source_mtime(source_path)
    if current_mtime is None:
        return True
    # mtime changed → stale
    if record.source_mtime is None or float(record.source_mtime) != current_mtime:
        return True
    return False


@dataclass
class DerivativeResult:
    id: int
    project_id: int
    photo_id: int
    kind: str
    path: str
    width: int
    height: int
    status: str
    # scale factor from source to derivative (1.0 means same size)
    scale: float = 1.0


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class DerivativeService:
    """Generate, cache and retrieve derivative images for a photo."""

    def __init__(self, db: Session, thumbnail_root: Optional[str] = None) -> None:
        self._db = db
        self._root = _derivative_root(
            thumbnail_root or global_settings.thumbnail_path
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_ai_thumbnail(
        self,
        photo: Photo,
        *,
        max_edge: Optional[int] = None,
        jpeg_quality: int = 85,
        force: bool = False,
    ) -> DerivativeResult:
        """Return (or generate) the ``ai_thumbnail`` derivative for *photo*."""
        effective_max_edge = max_edge or global_settings.ai_thumbnail_max_edge
        return self._get_or_create(
            photo=photo,
            kind=KIND_AI_THUMBNAIL,
            max_edge=effective_max_edge,
            min_edge=None,
            jpeg_quality=jpeg_quality,
            force=force,
        )

    def get_or_create_face_work_image(
        self,
        photo: Photo,
        *,
        max_edge: Optional[int] = None,
        min_edge: Optional[int] = None,
        jpeg_quality: Optional[int] = None,
        force: bool = False,
    ) -> DerivativeResult:
        """Return (or generate) the ``face_work_image`` derivative for *photo*.

        The resulting image is a JPEG with the long edge capped at *max_edge*
        (default: ``settings.face_work_image_max_edge``) and no smaller than
        *min_edge* (default: ``settings.face_work_image_min_edge``).  When the
        source image is smaller than *min_edge* the source is used as-is.
        """
        effective_max_edge = max_edge or global_settings.face_work_image_max_edge
        effective_min_edge = min_edge or global_settings.face_work_image_min_edge
        effective_quality = jpeg_quality or global_settings.face_work_image_jpeg_quality
        return self._get_or_create(
            photo=photo,
            kind=KIND_FACE_WORK_IMAGE,
            max_edge=effective_max_edge,
            min_edge=effective_min_edge,
            jpeg_quality=effective_quality,
            force=force,
        )

    def create_face_crop(
        self,
        *,
        project_id: int,
        photo_id: int,
        face_detection: FaceDetection,
        source_bgr: np.ndarray,
        source_width: int,
        source_height: int,
        crop_size: Optional[int] = None,
        jpeg_quality: int = 95,
    ) -> DerivativeResult:
        """Crop and save a face region as a ``face_crop`` derivative.

        Parameters
        ----------
        source_bgr:
            The BGR NumPy array from which to extract the crop.  This should be
            the ``face_work_image`` pixel data (same dimensions).
        source_width / source_height:
            Dimensions of *source_bgr* — used to clamp bbox coordinates.
        face_detection:
            The persisted ``FaceDetection`` row whose bbox defines the crop area.
        crop_size:
            Square target size after resizing.  Defaults to
            ``settings.face_crop_size`` (112 px).
        """
        import cv2  # lazy import to keep module importable without cv2

        effective_crop_size = crop_size or global_settings.face_crop_size

        # Clamp bbox to image bounds
        x = max(0, face_detection.bbox_x)
        y = max(0, face_detection.bbox_y)
        w = min(face_detection.bbox_w, source_width - x)
        h = min(face_detection.bbox_h, source_height - y)

        if w <= 0 or h <= 0:
            raise ValueError(
                f"Invalid face bbox for detection {face_detection.id}: "
                f"x={x} y={y} w={w} h={h} (source {source_width}x{source_height})"
            )

        crop_bgr = source_bgr[y : y + h, x : x + w]
        # Resize to square target
        crop_resized = cv2.resize(
            crop_bgr,
            (effective_crop_size, effective_crop_size),
            interpolation=cv2.INTER_LINEAR,
        )

        dest_path = _stable_crop_path(self._root, project_id, face_detection.id)
        # Convert BGR → RGB for PIL save
        crop_rgb = crop_resized[:, :, ::-1]
        pil_crop = Image.fromarray(crop_rgb, mode="RGB")
        pil_crop.save(str(dest_path), "JPEG", quality=jpeg_quality, optimize=True)

        # Upsert the derivative record
        record = self._upsert_face_crop_record(
            project_id=project_id,
            photo_id=photo_id,
            face_detection_id=face_detection.id,
            path=str(dest_path),
            width=effective_crop_size,
            height=effective_crop_size,
            quality=jpeg_quality,
        )

        return DerivativeResult(
            id=record.id,
            project_id=project_id,
            photo_id=photo_id,
            kind=KIND_FACE_CROP,
            path=str(dest_path),
            width=effective_crop_size,
            height=effective_crop_size,
            status="ready",
            scale=1.0,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create(
        self,
        *,
        photo: Photo,
        kind: str,
        max_edge: int,
        min_edge: Optional[int],
        jpeg_quality: int,
        force: bool,
    ) -> DerivativeResult:
        record = (
            self._db.query(PhotoDerivative)
            .filter(
                PhotoDerivative.project_id == photo.project_id,
                PhotoDerivative.photo_id == photo.id,
                PhotoDerivative.kind == kind,
            )
            .first()
        )

        source_path = photo.file_path

        if record and not force and not _is_stale(record, source_path):
            # Cache hit
            return DerivativeResult(
                id=record.id,
                project_id=record.project_id,
                photo_id=record.photo_id,
                kind=record.kind,
                path=record.path,  # type: ignore[arg-type]
                width=record.width or 0,
                height=record.height or 0,
                status=record.status,
                scale=1.0,
            )

        # Generate (or regenerate) the derivative
        dest_path = _stable_path(self._root, photo.project_id, photo.id, kind)
        try:
            width, height, scale = self._write_resized_jpeg(
                source_path=source_path,
                dest_path=dest_path,
                max_edge=max_edge,
                min_edge=min_edge,
                jpeg_quality=jpeg_quality,
            )
            status = "ready"
            error_message = None
        except FileNotFoundError as exc:
            logger.warning(
                "Derivative source missing for photo_id=%s kind=%s: %s",
                photo.id,
                kind,
                exc,
            )
            status = "missing_source"
            error_message = str(exc)[:2000]
            width, height, scale = 0, 0, 1.0
        except Exception as exc:
            logger.error(
                "Derivative generation failed for photo_id=%s kind=%s: %s",
                photo.id,
                kind,
                exc,
                exc_info=True,
            )
            status = "failed"
            error_message = str(exc)[:2000]
            width, height, scale = 0, 0, 1.0

        record = self._upsert_record(
            record=record,
            project_id=photo.project_id,
            photo_id=photo.id,
            kind=kind,
            path=str(dest_path) if status == "ready" else None,
            format="jpeg",
            width=width,
            height=height,
            source_path=source_path,
            source_mtime=_source_mtime(source_path),
            quality=jpeg_quality,
            status=status,
            error_message=error_message,
        )

        if status != "ready":
            raise OSError(
                f"Could not generate {kind} derivative for photo {photo.id} "
                f"(project {photo.project_id}): {error_message}"
            )

        return DerivativeResult(
            id=record.id,
            project_id=record.project_id,
            photo_id=record.photo_id,
            kind=record.kind,
            path=str(dest_path),
            width=width,
            height=height,
            status="ready",
            scale=scale,
        )

    def _write_resized_jpeg(
        self,
        *,
        source_path: str,
        dest_path: Path,
        max_edge: int,
        min_edge: Optional[int],
        jpeg_quality: int,
    ) -> Tuple[int, int, float]:
        """Decode *source_path*, resize, and write a JPEG to *dest_path*.

        Returns ``(width, height, scale)`` where scale is the ratio
        ``dest_size / source_size``.
        """
        img = read_image_pil(source_path)
        src_w, src_h = img.size
        long_edge = max(src_w, src_h)

        # Determine target long edge
        if long_edge <= (min_edge or 0):
            # Source is smaller than min_edge; keep original size
            target_long = long_edge
        else:
            target_long = min(long_edge, max_edge)

        if target_long < long_edge:
            scale = target_long / long_edge
            new_w = max(1, round(src_w * scale))
            new_h = max(1, round(src_h * scale))
            img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            new_w, new_h = src_w, src_h
            scale = 1.0

        img.save(str(dest_path), "JPEG", quality=jpeg_quality, optimize=True)
        return new_w, new_h, scale

    def _upsert_record(
        self,
        *,
        record: Optional[PhotoDerivative],
        project_id: int,
        photo_id: int,
        kind: str,
        path: Optional[str],
        format: str,
        width: int,
        height: int,
        source_path: str,
        source_mtime: Optional[float],
        quality: int,
        status: str,
        error_message: Optional[str],
    ) -> PhotoDerivative:
        now = datetime.now(timezone.utc)
        if record is None:
            record = PhotoDerivative(
                project_id=project_id,
                photo_id=photo_id,
                kind=kind,
            )
            self._db.add(record)
        record.path = path
        record.format = format
        record.width = width
        record.height = height
        record.source_path = source_path
        record.source_mtime = source_mtime  # type: ignore[assignment]
        record.quality = quality
        record.status = status
        record.error_message = error_message
        record.updated_at = now
        self._db.flush()
        return record

    def _upsert_face_crop_record(
        self,
        *,
        project_id: int,
        photo_id: int,
        face_detection_id: int,
        path: str,
        width: int,
        height: int,
        quality: int,
    ) -> PhotoDerivative:
        record = (
            self._db.query(PhotoDerivative)
            .filter(
                PhotoDerivative.project_id == project_id,
                PhotoDerivative.photo_id == photo_id,
                PhotoDerivative.face_detection_id == face_detection_id,
                PhotoDerivative.kind == KIND_FACE_CROP,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        if record is None:
            record = PhotoDerivative(
                project_id=project_id,
                photo_id=photo_id,
                kind=KIND_FACE_CROP,
                face_detection_id=face_detection_id,
            )
            self._db.add(record)
        record.path = path
        record.format = "jpeg"
        record.width = width
        record.height = height
        record.quality = quality
        record.status = "ready"
        record.error_message = None
        record.updated_at = now
        self._db.flush()
        return record
