from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.database import Base  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_library_path import ProjectLibraryPath  # noqa: E402
from app.schemas.project import ProjectCreate, ProjectUpdate  # noqa: E402
from app.services.library_path_rules import (  # noqa: E402
    normalize_library_path,
    normalize_library_paths,
)
from app.services.project_app_service import ProjectAppService  # noqa: E402
from app.services.project_library_service import (  # noqa: E402
    build_project_response,
    get_project_library_paths,
    sync_project_library_paths,
)
from app.services.project_photo_asset_service import (  # noqa: E402
    PhotoPathOwnershipError,
    ProjectPhotoAssetService,
)
from app.services.scanner import _resolve_scan_roots  # noqa: E402


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(type_, compiler, **kw):  # noqa: ANN001
    """SQLite needs INTEGER (not BIGINT) primary keys to autoincrement."""
    return "INTEGER"


def _make_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[Project.__table__, ProjectLibraryPath.__table__]
    )
    return sessionmaker(bind=engine)()


class LibraryPathRulesTest(unittest.TestCase):
    def test_normalize_strips_and_drops_trailing_slash(self) -> None:
        self.assertEqual(normalize_library_path("  /nas/photos/ "), "/nas/photos")

    def test_normalize_rejects_relative_path(self) -> None:
        with self.assertRaises(ValueError):
            normalize_library_path("nas/photos")

    def test_normalize_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            normalize_library_path("/nas/../etc")

    def test_normalize_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            normalize_library_path("   / ")

    def test_list_dedupes_preserving_order(self) -> None:
        self.assertEqual(
            normalize_library_paths(["/a", "/b/", "/a"]),
            ["/a", "/b"],
        )

    def test_list_rejects_empty_set(self) -> None:
        with self.assertRaises(ValueError):
            normalize_library_paths([])


class ProjectLibraryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _make_db()
        self.project = Project(
            name="p", photo_library_path="/legacy", thumbnail_path="/tmp"
        )
        self.db.add(self.project)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_get_falls_back_to_legacy_column_without_rows(self) -> None:
        self.assertEqual(get_project_library_paths(self.db, self.project), ["/legacy"])

    def test_sync_creates_ordered_rows_and_mirrors_primary(self) -> None:
        synced = sync_project_library_paths(
            self.db, self.project, ["/primary", "/secondary"]
        )
        self.db.commit()

        self.assertEqual(synced, ["/primary", "/secondary"])
        self.assertEqual(self.project.photo_library_path, "/primary")
        self.assertEqual(
            get_project_library_paths(self.db, self.project),
            ["/primary", "/secondary"],
        )

    def test_sync_replaces_previous_set(self) -> None:
        sync_project_library_paths(self.db, self.project, ["/one", "/two"])
        sync_project_library_paths(self.db, self.project, ["/three"])
        self.db.commit()

        rows = (
            self.db.query(ProjectLibraryPath)
            .filter(ProjectLibraryPath.project_id == self.project.id)
            .order_by(ProjectLibraryPath.position.asc())
            .all()
        )
        self.assertEqual([row.path for row in rows], ["/three"])


class ProjectCreateSchemaTest(unittest.TestCase):
    def test_requires_at_least_one_library_field(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCreate(name="p")

    def test_accepts_legacy_single_path(self) -> None:
        body = ProjectCreate(name="p", photo_library_path="/nas/a")
        self.assertEqual(body.effective_library_paths(), ["/nas/a"])

    def test_accepts_multi_path_list(self) -> None:
        body = ProjectCreate(
            name="p", photo_library_paths=["/nas/a", "/nas/b"]
        )
        self.assertEqual(body.effective_library_paths(), ["/nas/a", "/nas/b"])

    def test_rejects_mismatched_primary(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCreate(
                name="p",
                photo_library_path="/nas/a",
                photo_library_paths=["/nas/b", "/nas/c"],
            )

    def test_rejects_relative_entry_in_list(self) -> None:
        with self.assertRaises(ValidationError):
            ProjectCreate(name="p", photo_library_paths=["/nas/a", "relative"])


class ProjectAppServiceMultiPathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = _make_db()
        self.service = ProjectAppService(self.db)

    def tearDown(self) -> None:
        self.db.close()

    def test_create_with_multiple_paths(self) -> None:
        body = ProjectCreate(
            name="multi",
            photo_library_paths=["/nas/one", "/nas/two", "/nas/three"],
        )
        project = self.service.create_project(body)

        self.assertEqual(project.photo_library_path, "/nas/one")
        self.assertEqual(
            get_project_library_paths(self.db, project),
            ["/nas/one", "/nas/two", "/nas/three"],
        )

    def test_create_with_legacy_field_seeds_single_row(self) -> None:
        body = ProjectCreate(name="legacy", photo_library_path="/nas/only")
        project = self.service.create_project(body)

        self.assertEqual(
            get_project_library_paths(self.db, project), ["/nas/only"]
        )

    def test_update_full_replacement_via_list(self) -> None:
        project = self.service.create_project(
            ProjectCreate(
                name="p", photo_library_paths=["/nas/a", "/nas/b"]
            )
        )
        self.service.update_project(
            project.id, ProjectUpdate(photo_library_paths=["/nas/x"])
        )

        refreshed = self.service.get_project(project.id)
        self.assertEqual(refreshed.photo_library_path, "/nas/x")
        self.assertEqual(get_project_library_paths(self.db, refreshed), ["/nas/x"])

    def test_update_legacy_field_replaces_primary_only(self) -> None:
        project = self.service.create_project(
            ProjectCreate(
                name="p", photo_library_paths=["/nas/a", "/nas/b", "/nas/c"]
            )
        )
        self.service.update_project(
            project.id, ProjectUpdate(photo_library_path="/nas/new")
        )

        refreshed = self.service.get_project(project.id)
        self.assertEqual(refreshed.photo_library_path, "/nas/new")
        self.assertEqual(
            get_project_library_paths(self.db, refreshed),
            ["/nas/new", "/nas/b", "/nas/c"],
        )

    def test_response_includes_full_path_list(self) -> None:
        project = self.service.create_project(
            ProjectCreate(
                name="p", photo_library_paths=["/nas/a", "/nas/b"]
            )
        )
        response = build_project_response(self.db, project)
        self.assertEqual(response.photo_library_path, "/nas/a")
        self.assertEqual(response.photo_library_paths, ["/nas/a", "/nas/b"])


class ResolveScanRootsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        (root / "outer" / "nested").mkdir(parents=True)
        (root / "other").mkdir()
        self.outer = root / "outer"
        self.nested = root / "outer" / "nested"
        self.other = root / "other"
        self.missing = root / "does-not-exist"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_splits_available_and_missing(self) -> None:
        available, missing = _resolve_scan_roots(
            [str(self.outer), str(self.missing)]
        )
        self.assertEqual(available, [self.outer])
        self.assertEqual(missing, [self.missing])

    def test_dedupes_nested_roots_keeping_outer(self) -> None:
        available, _ = _resolve_scan_roots(
            [str(self.outer), str(self.nested)]
        )
        self.assertEqual(available, [self.outer])

    def test_dedupes_nested_roots_regardless_of_order(self) -> None:
        available, _ = _resolve_scan_roots(
            [str(self.nested), str(self.outer)]
        )
        self.assertEqual(available, [self.outer])

    def test_dedupes_duplicate_roots(self) -> None:
        available, _ = _resolve_scan_roots(
            [str(self.other), str(self.other)]
        )
        self.assertEqual(available, [self.other])


class AssetServiceMultiRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.library_a = root / "lib-a"
        self.library_b = root / "lib-b"
        self.outside = root / "outside"
        self.thumbs = root / "thumbs"
        for path in (self.library_a, self.library_b, self.outside, self.thumbs):
            path.mkdir()

        self.db = _make_db()
        self.project = Project(
            name="p",
            photo_library_path=str(self.library_a),
            thumbnail_path=str(self.thumbs),
        )
        self.db.add(self.project)
        self.db.commit()
        sync_project_library_paths(
            self.db, self.project, [str(self.library_a), str(self.library_b)]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def _photo(self, file_path: Path) -> SimpleNamespace:
        return SimpleNamespace(
            file_path=str(file_path),
            file_name=file_path.name,
            mime_type="image/jpeg",
            thumbnail_path=None,
        )

    def test_file_under_second_root_is_allowed(self) -> None:
        photo_path = self.library_b / "second.jpg"
        photo_path.write_bytes(b"jpeg")

        asset = ProjectPhotoAssetService(self.db).get_original_asset(
            project=self.project, photo=self._photo(photo_path)
        )
        self.assertEqual(asset.path, str(photo_path))

    def test_file_outside_all_roots_is_rejected(self) -> None:
        photo_path = self.outside / "escape.jpg"
        photo_path.write_bytes(b"jpeg")

        with self.assertRaises(PhotoPathOwnershipError):
            ProjectPhotoAssetService(self.db).get_original_asset(
                project=self.project, photo=self._photo(photo_path)
            )


if __name__ == "__main__":
    unittest.main()
