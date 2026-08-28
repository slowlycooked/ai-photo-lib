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


class PhotoPathOwnershipError(PermissionError):
    pass


def _ensure_path_within(path: str | None, root: str | None, label: str) -> str:
    if not path or not root:
        raise PhotoPathOwnershipError(f"{label} is outside the project path")

    resolved_path = Path(path).resolve()
    resolved_root = Path(root).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PhotoPathOwnershipError(f"{label} is outside the project path") from exc
    return path


class ProjectPhotoAssetService:
    _INLINE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
    _CONVERT_SUFFIXES = {".heic", ".heif"}

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def get_thumbnail_asset(self, *, project: Project, photo: Photo) -> PhotoFileAsset:
        original_path = _ensure_path_within(
            photo.file_path,
            project.photo_library_path,
            "Original file",
        )
        if not project.thumbnail_path:
            raise PhotoPathOwnershipError("Thumbnail root is outside the project path")
        if photo.thumbnail_path:
            _ensure_path_within(
                photo.thumbnail_path,
                project.thumbnail_path,
                "Thumbnail file",
            )

        if not photo.thumbnail_path or not Path(photo.thumbnail_path).exists():
            if not Path(original_path).exists():
                raise FileNotFoundError("Thumbnail not available")
            thumb = generate_thumbnail(
                original_path,
                project_id=project.id,
                thumbnail_root=project.thumbnail_path,
            )
            if not thumb:
                raise FileNotFoundError("Thumbnail not available")
            _ensure_path_within(thumb, project.thumbnail_path, "Thumbnail file")
            photo.thumbnail_path = thumb
            if self._db is None:
                raise RuntimeError("Database session is required to persist thumbnail path")
            self._db.commit()

        return PhotoFileAsset(
            path=photo.thumbnail_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=86400, stale-while-revalidate=604800"
            },
        )

    def get_original_asset(self, *, project: Project, photo: Photo) -> PhotoFileAsset:
        original_path = _ensure_path_within(
            photo.file_path,
            project.photo_library_path,
            "Original file",
        )
        if not Path(original_path).exists():
            raise FileNotFoundError("Original file not found on disk")

        return PhotoFileAsset(
            path=original_path,
            media_type=photo.mime_type or "application/octet-stream",
            filename=photo.file_name,
            headers={
                "Cache-Control": "private, max-age=0",
                "Content-Disposition": f'attachment; filename="{photo.file_name}"',
            },
        )

    def get_preview_asset(
        self, *, project: Project, photo: Photo
    ) -> PhotoFileAsset | PhotoBytesAsset:
        original_path = _ensure_path_within(
            photo.file_path,
            project.photo_library_path,
            "Original file",
        )
        if not Path(original_path).exists():
            raise FileNotFoundError("Original file not found on disk")

        suffix = Path(original_path).suffix.lower()
        mime = photo.mime_type or ""
        headers = {
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        }

        if (
            mime.startswith("video/")
            or (mime in self._INLINE_MIME and suffix not in self._CONVERT_SUFFIXES)
        ):
            return PhotoFileAsset(path=original_path, media_type=mime, headers=headers)

        try:
            with Image.open(original_path) as img:
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
