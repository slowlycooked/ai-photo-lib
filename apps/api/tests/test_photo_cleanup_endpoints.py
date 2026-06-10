from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from collections.abc import Generator
from pathlib import Path

import sqlalchemy as sa
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.api.deps import require_project, require_project_manager  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_task import ProjectTask  # noqa: E402
from app.services.project_task_app_service import ProjectTaskAppService  # noqa: E402
from app.services.project_task_service import TASK_TYPE_LIBRARY_SCAN  # noqa: E402
from app.services.scanner import scan_project  # noqa: E402


SCHEMA_SQL = """
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  photo_library_path TEXT NOT NULL,
  thumbnail_path TEXT,
  is_default BOOLEAN NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at TEXT
);

CREATE TABLE project_folders (
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  parent_id INTEGER,
  name TEXT,
  relative_path TEXT,
  depth INTEGER,
  photo_count_direct INTEGER,
  photo_count_recursive INTEGER,
  created_at TEXT,
  updated_at TEXT,
  deleted_at TEXT
);

CREATE TABLE photos (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_hash TEXT,
  file_size INTEGER,
  mime_type TEXT,
  width INTEGER,
  height INTEGER,
  taken_at TEXT,
  exif TEXT,
  thumbnail_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  gps_latitude REAL,
  gps_longitude REAL,
  gps_altitude REAL,
  country_code TEXT,
  country_name TEXT,
  admin1 TEXT,
  admin2 TEXT,
  city TEXT,
  district TEXT,
  formatted_address TEXT,
  location_source TEXT,
  location_resolved_at TEXT,
  camera_make TEXT,
  camera_model TEXT,
  lens_model TEXT,
  focal_length TEXT,
  aperture TEXT,
  exposure_time TEXT,
  iso INTEGER,
  orientation INTEGER,
  folder_id INTEGER,
  relative_path TEXT,
  folder_path TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at TEXT
);

CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    retry_count INTEGER NOT NULL DEFAULT 0,
    request_params TEXT,
    progress_payload TEXT,
    result_payload TEXT,
    error_message TEXT,
    locked_by TEXT,
    locked_at TEXT,
    heartbeat_at TEXT,
    lease_expires_at TEXT,
    last_error_code TEXT,
    last_error_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_project_tasks_project_type_status
    ON project_tasks (project_id, task_type, status);

CREATE UNIQUE INDEX uq_project_tasks_one_active_scan
    ON project_tasks (project_id)
    WHERE task_type IN ('library_scan', 'library_reindex')
        AND status IN ('queued', 'running');
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class PhotoDeleteEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmp_dir.name) / "test.db"
        self._lib = Path(self._tmp_dir.name) / "library"
        self._thumbs = Path(self._tmp_dir.name) / "thumbs"
        self._lib.mkdir(parents=True, exist_ok=True)
        self._thumbs.mkdir(parents=True, exist_ok=True)

        self._engine = sa.create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            future=True,
        )

        with self._engine.begin() as conn:
            for stmt in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
                conn.execute(sa.text(stmt))

            conn.execute(
                sa.text(
                    """
                    INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
                    VALUES (1, 'Project A', :lib, :thumb, 1)
                    """
                ),
                {"lib": str(self._lib), "thumb": str(self._thumbs)},
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
                    VALUES (2, 'Project B', :lib, :thumb, 0)
                    """
                ),
                {"lib": str(self._lib), "thumb": str(self._thumbs)},
            )

        self._original = self._lib / "manual-delete.jpg"
        Image.new("RGB", (80, 60), color=(100, 140, 200)).save(self._original, "JPEG")
        self._thumb = self._thumbs / "manual-delete-thumb.jpg"
        Image.new("RGB", (40, 30), color=(80, 120, 160)).save(self._thumb, "JPEG")

        self._batch_original = self._lib / "manual-delete-batch.jpg"
        Image.new("RGB", (88, 66), color=(90, 150, 210)).save(self._batch_original, "JPEG")
        self._batch_thumb = self._thumbs / "manual-delete-batch-thumb.jpg"
        Image.new("RGB", (44, 33), color=(70, 110, 170)).save(self._batch_thumb, "JPEG")

        self._project2_original = self._lib / "project2-keep.jpg"
        Image.new("RGB", (84, 64), color=(120, 180, 90)).save(self._project2_original, "JPEG")
        self._project2_thumb = self._thumbs / "project2-keep-thumb.jpg"
        Image.new("RGB", (42, 32), color=(90, 120, 80)).save(self._project2_thumb, "JPEG")

        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO photos (
                      id, project_id, file_path, file_name, file_hash, file_size,
                      mime_type, width, height, thumbnail_path, status
                    )
                    VALUES (
                      101, 1, :file_path, 'manual-delete.jpg', :file_hash, :file_size,
                      'image/jpeg', 80, 60, :thumb_path, 'indexed'
                    )
                    """
                ),
                {
                    "file_path": str(self._original),
                    "file_hash": _sha256(self._original),
                    "file_size": self._original.stat().st_size,
                    "thumb_path": str(self._thumb),
                },
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO photos (
                      id, project_id, file_path, file_name, file_hash, file_size,
                      mime_type, width, height, thumbnail_path, status
                    )
                    VALUES (
                      102, 1, :file_path, 'manual-delete-batch.jpg', :file_hash, :file_size,
                      'image/jpeg', 88, 66, :thumb_path, 'indexed'
                    )
                    """
                ),
                {
                    "file_path": str(self._batch_original),
                    "file_hash": _sha256(self._batch_original),
                    "file_size": self._batch_original.stat().st_size,
                    "thumb_path": str(self._batch_thumb),
                },
            )
            conn.execute(
                sa.text(
                    """
                    INSERT INTO photos (
                      id, project_id, file_path, file_name, file_hash, file_size,
                      mime_type, width, height, thumbnail_path, status
                    )
                    VALUES (
                      201, 2, :file_path, 'project2-keep.jpg', :file_hash, :file_size,
                      'image/jpeg', 84, 64, :thumb_path, 'indexed'
                    )
                    """
                ),
                {
                    "file_path": str(self._project2_original),
                    "file_hash": _sha256(self._project2_original),
                    "file_size": self._project2_original.stat().st_size,
                    "thumb_path": str(self._project2_thumb),
                },
            )

        def override_get_db() -> Generator[Session, None, None]:
            db = self._SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_require_project_manager(project_id: int) -> Project:
            db = self._SessionLocal()
            try:
                project = (
                    db.query(Project)
                    .filter(Project.id == project_id, Project.deleted_at.is_(None))
                    .first()
                )
                if project is None:
                    raise RuntimeError("Project not found")
                return project
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_project] = override_require_project_manager
        app.dependency_overrides[require_project_manager] = override_require_project_manager
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self._engine.dispose()
        self._tmp_dir.cleanup()

    def _count_photo(self, photo_id: int) -> int:
        with self._engine.connect() as conn:
            return int(
                conn.execute(
                    sa.text("SELECT COUNT(1) FROM photos WHERE id = :id"),
                    {"id": photo_id},
                ).scalar_one()
            )

    def test_delete_photo_record_keeps_original_by_default(self) -> None:
        res = self.client.delete("/projects/1/photos/101")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["deleted_original"])
        self.assertTrue(body["deleted_thumbnail"])

        self.assertEqual(self._count_photo(101), 0)
        self.assertTrue(self._original.exists())
        self.assertFalse(self._thumb.exists())

    def test_delete_photo_record_can_delete_original_when_requested(self) -> None:
        res = self.client.delete("/projects/1/photos/101?delete_original=true")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["deleted_original"])
        self.assertTrue(body["deleted_thumbnail"])

        self.assertEqual(self._count_photo(101), 0)
        self.assertFalse(self._original.exists())
        self.assertFalse(self._thumb.exists())

    def test_delete_photo_record_post_compat_endpoint(self) -> None:
        res = self.client.post("/projects/1/photos/101/delete")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["deleted_original"])
        self.assertTrue(body["deleted_thumbnail"])

        self.assertEqual(self._count_photo(101), 0)
        self.assertTrue(self._original.exists())
        self.assertFalse(self._thumb.exists())

    def test_batch_delete_photo_records_and_originals(self) -> None:
        res = self.client.post(
            "/projects/1/photos/batch-delete",
            json={"photo_ids": [101, 102], "delete_original": True},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["requested_count"], 2)
        self.assertEqual(body["deleted_count"], 2)
        self.assertEqual(body["deleted_original_count"], 2)
        self.assertEqual(body["deleted_thumbnail_count"], 2)
        self.assertEqual(body["not_found_photo_ids"], [])

        self.assertEqual(self._count_photo(101), 0)
        self.assertEqual(self._count_photo(102), 0)
        self.assertFalse(self._original.exists())
        self.assertFalse(self._thumb.exists())
        self.assertFalse(self._batch_original.exists())
        self.assertFalse(self._batch_thumb.exists())

    def test_batch_delete_keeps_project_isolation(self) -> None:
        res = self.client.post(
            "/projects/1/photos/batch-delete",
            json={"photo_ids": [101, 201], "delete_original": True},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["requested_count"], 2)
        self.assertEqual(body["deleted_count"], 1)
        self.assertEqual(body["deleted_photo_ids"], [101])
        self.assertEqual(body["not_found_photo_ids"], [201])

        self.assertEqual(self._count_photo(101), 0)
        self.assertEqual(self._count_photo(201), 1)
        self.assertTrue(self._project2_original.exists())
        self.assertTrue(self._project2_thumb.exists())

    def test_scan_start_and_status_expose_fail_fast_config_error(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE projects SET thumbnail_path = '' WHERE id = 1"),
            )

        start_res = self.client.post("/projects/1/scan/start")
        self.assertEqual(start_res.status_code, 200)

        db = self._SessionLocal()
        try:
            task = (
                db.query(ProjectTask)
                .filter(
                    ProjectTask.project_id == 1,
                    ProjectTask.task_type == TASK_TYPE_LIBRARY_SCAN,
                )
                .order_by(ProjectTask.id.desc())
                .first()
            )
            self.assertIsNotNone(task)
            assert task is not None
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)
        finally:
            db.close()

        status_res = self.client.get("/projects/1/scan/status")
        self.assertEqual(status_res.status_code, 200)
        status_body = status_res.json()
        self.assertFalse(status_body["running"])
        self.assertGreaterEqual(int(status_body.get("errors") or 0), 1)
        self.assertIn("Missing required project thumbnail_path", status_body.get("message", ""))

    def test_scan_start_rejects_invalid_project_library_path_with_actionable_error(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE projects SET photo_library_path = '/photos' WHERE id = 1"),
            )

        res = self.client.post("/projects/1/scan/start")
        self.assertEqual(res.status_code, 422)
        detail = str(res.json().get("detail") or "")
        self.assertIn("photo_library_path not found or not a directory", detail)
        self.assertIn("project path differs from configured PHOTO_LIBRARY_PATH", detail)

    def test_reindex_rejects_invalid_project_library_path_with_actionable_error(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE projects SET photo_library_path = '/photos' WHERE id = 1"),
            )

        res = self.client.post("/projects/1/scan/reindex?scope=all")
        self.assertEqual(res.status_code, 422)
        detail = str(res.json().get("detail") or "")
        self.assertIn("photo_library_path not found or not a directory", detail)
        self.assertIn("project path differs from configured PHOTO_LIBRARY_PATH", detail)


class ScanCleanupTest(unittest.TestCase):
    def test_scan_removes_missing_photo_records_and_thumbnails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "scan.db"
            library = Path(tmp_dir) / "library"
            thumbs = Path(tmp_dir) / "thumbs"
            library.mkdir(parents=True, exist_ok=True)
            thumbs.mkdir(parents=True, exist_ok=True)

            existing = library / "kept.jpg"
            Image.new("RGB", (64, 48), color=(200, 120, 90)).save(existing, "JPEG")

            stale_original = library / "deleted.jpg"
            stale_thumb = thumbs / "deleted-thumb.jpg"
            Image.new("RGB", (32, 24), color=(110, 100, 90)).save(stale_thumb, "JPEG")

            engine = sa.create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
            SessionLocal = sessionmaker(
                bind=engine,
                autocommit=False,
                autoflush=False,
                future=True,
            )

            with engine.begin() as conn:
                for stmt in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
                    conn.execute(sa.text(stmt))

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
                        VALUES (1, 'Project A', :lib, :thumb, 0)
                        """
                    ),
                    {"lib": str(library), "thumb": str(thumbs)},
                )

                conn.execute(
                    sa.text(
                        """
                        INSERT INTO photos (
                          id, project_id, file_path, file_name, file_hash, file_size,
                          mime_type, width, height, thumbnail_path, status
                        )
                        VALUES (
                          201, 1, :stale_file, 'deleted.jpg', :stale_hash, 10,
                          'image/jpeg', 32, 24, :stale_thumb, 'indexed'
                        )
                        """
                    ),
                    {
                        "stale_file": str(stale_original),
                        "stale_hash": "stale-hash",
                        "stale_thumb": str(stale_thumb),
                    },
                )

            db = SessionLocal()
            try:
                state = scan_project(db, 1)
            finally:
                db.close()

            self.assertFalse(state["running"])

            with engine.connect() as conn:
                stale_count = int(
                    conn.execute(
                        sa.text("SELECT COUNT(1) FROM photos WHERE id = 201"),
                    ).scalar_one()
                )
                new_count = int(
                    conn.execute(
                        sa.text(
                            "SELECT COUNT(1) FROM photos WHERE project_id = 1 AND file_name = 'kept.jpg'"
                        ),
                    ).scalar_one()
                )

            self.assertEqual(stale_count, 0)
            self.assertEqual(new_count, 1)
            self.assertFalse(stale_thumb.exists())
            self.assertTrue(existing.exists())

            engine.dispose()


if __name__ == "__main__":
    unittest.main()
