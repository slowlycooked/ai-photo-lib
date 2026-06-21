from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.photo import Photo  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.scanner import PreparedScanFile, StructuredExif, scan_project  # noqa: E402


class _StopScan(RuntimeError):
    pass


class ScannerPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_file.close()
        self._engine = create_engine(
            f"sqlite:///{self._db_file.name}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            future=True,
        )
        Project.__table__.create(self._engine)
        Photo.__table__.create(self._engine)

        self._tmpdir = tempfile.TemporaryDirectory()
        self._library = Path(self._tmpdir.name) / "library"
        self._thumbs = Path(self._tmpdir.name) / "thumbs"
        self._library.mkdir(parents=True, exist_ok=True)
        self._thumbs.mkdir(parents=True, exist_ok=True)

        db = self._SessionLocal()
        db.add(
            Project(
                id=1,
                name="Project A",
                description=None,
                photo_library_path=str(self._library),
                thumbnail_path=str(self._thumbs),
                is_default=True,
            )
        )
        db.commit()
        db.close()

    def tearDown(self) -> None:
        self._engine.dispose()
        self._tmpdir.cleanup()
        if os.path.exists(self._db_file.name):
            os.unlink(self._db_file.name)

    def _create_files(self, names: list[str]) -> None:
        for name in names:
            path = self._library / name
            path.write_bytes(b"fake-image")

    def test_scan_project_prepares_files_concurrently(self) -> None:
        self._create_files(["a.jpg", "b.jpg", "c.jpg"])
        db = self._SessionLocal()

        lock = threading.Lock()
        release = threading.Event()
        active = 0
        max_active = 0
        call_count = 0

        def fake_prepare(file_path, **kwargs):
            nonlocal active, max_active, call_count
            with lock:
                active += 1
                call_count += 1
                max_active = max(max_active, active)
                local_call = call_count
                if active >= 2:
                    release.set()
            try:
                if local_call <= 2:
                    self.assertTrue(release.wait(timeout=1.0))
                return PreparedScanFile(
                    path=file_path,
                    path_str=str(file_path),
                    relative_path=file_path.name,
                    folder_path="",
                    file_hash=f"hash-{file_path.name}",
                    file_size=10,
                    mime_type="image/jpeg",
                    width=32,
                    height=24,
                    exif=StructuredExif(),
                    thumbnail_path=str(self._thumbs / f"{file_path.stem}.jpg"),
                    action="upsert",
                    latency_ms=1,
                )
            finally:
                with lock:
                    active -= 1

        def fake_persist(session, prepared, state, project_id):
            state["inserted"] += 1

        with patch("app.services.scanner._prepare_scan_file_with_retries", side_effect=fake_prepare), patch(
            "app.services.scanner._persist_prepared_file",
            side_effect=fake_persist,
        ), patch("app.services.scanner.cleanup_missing_project_photos"), patch(
            "app.services.scanner.settings.scan_thumbnail_concurrency",
            2,
        ), patch("app.services.scanner.settings.scan_queue_max_size", 8), patch(
            "app.services.scanner.settings.scan_db_write_batch_size",
            20,
        ), patch("app.services.folder_service.recompute_project_folder_counts"):
            state = scan_project(db, 1)

        self.assertEqual(state["scanned"], 3)
        self.assertEqual(state["discovered_count"], 3)
        self.assertEqual(state["prepared_count"], 3)
        self.assertEqual(state["persisted_count"], 3)
        self.assertEqual(state["inserted"], 3)
        self.assertEqual(state["errors"], 0)
        self.assertGreaterEqual(max_active, 2)
        self.assertEqual(state["current_stage"], "done")
        db.close()

    def test_scan_project_flushes_remaining_batch_at_end(self) -> None:
        self._create_files(["a.jpg", "b.jpg", "c.jpg"])
        db = self._SessionLocal()
        original_commit = db.commit
        commit_calls: list[int] = []

        def counting_commit():
            commit_calls.append(1)
            return original_commit()

        db.commit = counting_commit  # type: ignore[assignment]

        def fake_prepare(file_path, **kwargs):
            return PreparedScanFile(
                path=file_path,
                path_str=str(file_path),
                relative_path=file_path.name,
                folder_path="",
                file_hash=f"hash-{file_path.name}",
                file_size=10,
                mime_type="image/jpeg",
                width=32,
                height=24,
                exif=StructuredExif(),
                thumbnail_path=str(self._thumbs / f"{file_path.stem}.jpg"),
                action="upsert",
                latency_ms=1,
            )

        def fake_persist(session, prepared, state, project_id):
            state["inserted"] += 1

        with patch("app.services.scanner._prepare_scan_file_with_retries", side_effect=fake_prepare), patch(
            "app.services.scanner._persist_prepared_file",
            side_effect=fake_persist,
        ), patch("app.services.scanner.cleanup_missing_project_photos"), patch(
            "app.services.scanner.settings.scan_thumbnail_concurrency",
            1,
        ), patch("app.services.scanner.settings.scan_queue_max_size", 8), patch(
            "app.services.scanner.settings.scan_db_write_batch_size",
            20,
        ), patch("app.services.folder_service.recompute_project_folder_counts"):
            state = scan_project(db, 1)

        self.assertEqual(state["inserted"], 3)
        self.assertEqual(state["discovered_count"], 3)
        self.assertEqual(state["prepared_count"], 3)
        self.assertEqual(state["persisted_count"], 3)
        self.assertEqual(len(commit_calls), 2)
        self.assertEqual(state["current_stage"], "done")
        db.close()

    def test_scan_project_propagates_abort_and_stops_submitting_new_work(self) -> None:
        self._create_files(["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
        db = self._SessionLocal()
        prepared_calls: list[str] = []

        def fake_prepare(file_path, **kwargs):
            prepared_calls.append(file_path.name)
            return PreparedScanFile(
                path=file_path,
                path_str=str(file_path),
                relative_path=file_path.name,
                folder_path="",
                file_hash=f"hash-{file_path.name}",
                file_size=10,
                mime_type="image/jpeg",
                width=32,
                height=24,
                exif=StructuredExif(),
                thumbnail_path=str(self._thumbs / f"{file_path.stem}.jpg"),
                action="upsert",
                latency_ms=7,
            )

        def fake_persist(session, prepared, state, project_id):
            state["inserted"] += 1

        def progress_callback(state):
            if state.get("current_stage") == "persist" and int(state.get("inserted") or 0) >= 1:
                raise _StopScan("cancel scan")

        with patch("app.services.scanner._prepare_scan_file_with_retries", side_effect=fake_prepare), patch(
            "app.services.scanner._persist_prepared_file",
            side_effect=fake_persist,
        ), patch("app.services.scanner.cleanup_missing_project_photos") as cleanup_mock, patch(
            "app.services.scanner.settings.scan_thumbnail_concurrency",
            1,
        ), patch("app.services.scanner.settings.scan_queue_max_size", 1), patch(
            "app.services.scanner.settings.scan_db_write_batch_size",
            20,
        ), patch("app.services.folder_service.recompute_project_folder_counts") as recompute_mock:
            with self.assertRaises(_StopScan):
                scan_project(db, 1, progress_callback=progress_callback)

        self.assertEqual(len(prepared_calls), 1)
        cleanup_mock.assert_not_called()
        recompute_mock.assert_not_called()
        db.close()


if __name__ == "__main__":
    unittest.main()