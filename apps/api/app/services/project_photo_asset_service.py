from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from ..models.photo import Photo
from ..models.project import Project
from .thumbnail import generate_thumbnail


@dataclass(frozen=True)
class PhotoFileAsset:
    path: str
    media_type: str
    headers: dict[str, str]
    filename: str | None = None


@dataclass(frozen=True)
class PhotoBytesAsset:
    content: bytes
    media_type: str
    headers: dict[str, str]


class PhotoPreviewConversionError(RuntimeError):
    pass


class ProjectPhotoAssetService:
    _INLINE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
    _CONVERT_SUFFIXES = {".heic", ".heif"}

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def get_thumbnail_asset(self, *, project: Project, photo: Photo) -> PhotoFileAsset:
        if not photo.thumbnail_path or not Path(photo.thumbnail_path).exists():
            if not Path(photo.file_path).exists():
                raise FileNotFoundError("Thumbnail not available")
            thumb = generate_thumbnail(
                photo.file_path,
                project_id=project.id,
                thumbnail_root=project.thumbnail_path,
            )
            if not thumb:
                raise FileNotFoundError("Thumbnail not available")
            photo.thumbnail_path = thumb
            if self._db is None:
                raise RuntimeError("Database session is required to persist thumbnail path")
            self._db.commit()

        return PhotoFileAsset(
            path=photo.thumbnail_path,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )

    def get_original_asset(self, *, photo: Photo) -> PhotoFileAsset:
        if not Path(photo.file_path).exists():
            raise FileNotFoundError("Original file not found on disk")

        return PhotoFileAsset(
            path=photo.file_path,
            media_type=photo.mime_type or "application/octet-stream",
            filename=photo.file_name,
            headers={
                "Cache-Control": "private, max-age=0",
                "Content-Disposition": f'attachment; filename="{photo.file_name}"',
            },
        )

    def get_preview_asset(self, *, photo: Photo) -> PhotoFileAsset | PhotoBytesAsset:
        if not Path(photo.file_path).exists():
            raise FileNotFoundError("Original file not found on disk")

        suffix = Path(photo.file_path).suffix.lower()
        mime = photo.mime_type or ""
        headers = {
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        }

        if mime in self._INLINE_MIME and suffix not in self._CONVERT_SUFFIXES:
            return PhotoFileAsset(path=photo.file_path, media_type=mime, headers=headers)

        try:
            with Image.open(photo.file_path) as img:
                img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=90, optimize=True)
                return PhotoBytesAsset(
                    content=buf.getvalue(),
                    media_type="image/jpeg",
                    headers=headers,
                )
        except Exception as exc:
            raise PhotoPreviewConversionError(f"Preview conversion failed: {exc}") from exc
