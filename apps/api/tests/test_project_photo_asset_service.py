from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.responses import FileResponse

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.project_photo_asset_service import (  # noqa: E402
    PhotoFileAsset,
    PhotoPathOwnershipError,
    ProjectPhotoAssetService,
)
from app.routers.project_photos import (  # noqa: E402
    _photo_file_response,
    get_project_photo_thumbnail,
)


class ProjectPhotoAssetServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._library = self._root / "library"
        self._thumbs = self._root / "thumbs"
        self._outside = self._root / "outside"
        self._library.mkdir()
        self._thumbs.mkdir()
        self._outside.mkdir()
        self.project = SimpleNamespace(
            id=1,
            photo_library_path=str(self._library),
            thumbnail_path=str(self._thumbs),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _photo(
        self,
        *,
        file_path: Path,
        thumbnail_path: Path | None = None,
        mime_type: str = "image/jpeg",
    ) -> SimpleNamespace:
        return SimpleNamespace(
            file_path=str(file_path),
            file_name=file_path.name,
            mime_type=mime_type,
            thumbnail_path=str(thumbnail_path) if thumbnail_path else None,
        )

    def test_original_asset_allows_photo_inside_project_library(self) -> None:
        photo_path = self._library / "inside.jpg"
        photo_path.write_bytes(b"jpeg")

        asset = ProjectPhotoAssetService().get_original_asset(
            project=self.project,
            photo=self._photo(file_path=photo_path),
        )

        self.assertEqual(asset.path, str(photo_path))

    def test_original_asset_rejects_photo_outside_project_library(self) -> None:
        photo_path = self._outside / "escape.jpg"
        photo_path.write_bytes(b"jpeg")

        with self.assertRaises(PhotoPathOwnershipError):
            ProjectPhotoAssetService().get_original_asset(
                project=self.project,
                photo=self._photo(file_path=photo_path),
            )

    def test_thumbnail_asset_rejects_thumbnail_outside_project_thumbnail_root(self) -> None:
        photo_path = self._library / "inside.jpg"
        thumb_path = self._outside / "thumb.jpg"
        photo_path.write_bytes(b"jpeg")
        thumb_path.write_bytes(b"jpeg")

        with self.assertRaises(PhotoPathOwnershipError):
            ProjectPhotoAssetService().get_thumbnail_asset(
                project=self.project,
                photo=self._photo(file_path=photo_path, thumbnail_path=thumb_path),
            )

    def test_thumbnail_asset_rejects_missing_project_thumbnail_root(self) -> None:
        photo_path = self._library / "inside.jpg"
        photo_path.write_bytes(b"jpeg")
        project = SimpleNamespace(
            id=1,
            photo_library_path=str(self._library),
            thumbnail_path="",
        )

        with self.assertRaises(PhotoPathOwnershipError):
            ProjectPhotoAssetService().get_thumbnail_asset(
                project=project,
                photo=self._photo(file_path=photo_path),
            )

    def test_thumbnail_asset_is_browser_cacheable(self) -> None:
        photo_path = self._library / "inside.jpg"
        thumb_path = self._thumbs / "thumb.jpg"
        photo_path.write_bytes(b"original")
        thumb_path.write_bytes(b"thumbnail")

        asset = ProjectPhotoAssetService().get_thumbnail_asset(
            project=self.project,
            photo=self._photo(file_path=photo_path, thumbnail_path=thumb_path),
        )

        self.assertEqual(
            asset.headers["Cache-Control"],
            "private, max-age=86400, stale-while-revalidate=604800",
        )

    def test_video_preview_streams_original_inline(self) -> None:
        video_path = self._library / "clip.mp4"
        video_path.write_bytes(b"video")

        asset = ProjectPhotoAssetService().get_preview_asset(
            project=self.project,
            photo=self._photo(file_path=video_path, mime_type="video/mp4"),
        )

        self.assertIsInstance(asset, PhotoFileAsset)
        self.assertEqual(asset.path, str(video_path))
        self.assertEqual(asset.media_type, "video/mp4")
        self.assertEqual(asset.headers["Content-Disposition"], "inline")

    def test_photo_file_response_streams_from_disk(self) -> None:
        photo_path = self._library / "inside.jpg"
        photo_path.write_bytes(b"jpeg")

        with patch.object(Path, "read_bytes", side_effect=AssertionError("must not buffer file")):
            response = _photo_file_response(
                PhotoFileAsset(
                    path=str(photo_path),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=60"},
                ),
                label="Thumbnail",
            )

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(Path(response.path), photo_path)

    def test_thumbnail_route_releases_db_before_building_file_response(self) -> None:
        asset = PhotoFileAsset(
            path=str(self._library / "inside.jpg"),
            media_type="image/jpeg",
            headers={},
        )
        db = Mock()

        def assert_db_closed(response_asset, *, label):
            db.close.assert_called_once_with()
            self.assertIs(response_asset, asset)
            self.assertEqual(label, "Thumbnail")
            return "response"

        with (
            patch(
                "app.routers.project_photos.ProjectPhotoAssetService.get_thumbnail_asset",
                return_value=asset,
            ),
            patch(
                "app.routers.project_photos._photo_file_response",
                side_effect=assert_db_closed,
            ),
        ):
            response = get_project_photo_thumbnail(
                project=self.project,
                photo=self._photo(file_path=self._library / "inside.jpg"),
                db=db,
            )

        self.assertEqual(response, "response")


if __name__ == "__main__":
    unittest.main()
