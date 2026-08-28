from __future__ import annotations

import os
import tempfile
import threading
import unittest
from datetime import datetime
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

    def test_scan_project_discovers_supported_video_files(self) -> None:
        self._create_files(["clip.mp4", "notes.txt"])
        db = self._SessionLocal()
        prepared_names: list[str] = []

        def fake_prepare(file_path, **kwargs):
            prepared_names.append(file_path.name)
            return PreparedScanFile(
                path=file_path,
                path_str=str(file_path),
                relative_path=file_path.name,
                folder_path="",
                file_hash=f"hash-{file_path.name}",
                file_size=10,
                mime_type="video/mp4",
                width=1920,
                height=1080,
                exif=StructuredExif(),
                thumbnail_path=str(self._thumbs / "clip.jpg"),
                action="upsert",
                latency_ms=1,
            )

        def fake_persist(session, prepared, state, project_id):
            state["inserted"] += 1

        with patch(
            "app.services.scanner._prepare_scan_file_with_retries",
            side_effect=fake_prepare,
        ), patch(
            "app.services.scanner._persist_prepared_file",
            side_effect=fake_persist,
        ), patch("app.services.scanner.cleanup_missing_project_photos"), patch(
            "app.services.folder_service.recompute_project_folder_counts"
        ):
            state = scan_project(db, 1)

        self.assertEqual(prepared_names, ["clip.mp4"])
        self.assertEqual(state["discovered_count"], 1)
        self.assertEqual(state["inserted"], 1)
        db.close()

    def test_scan_project_skips_soft_deleted_quarantined_photo(self) -> None:
        self._create_files(["quarantined.jpg"])
        photo_path = self._library / "quarantined.jpg"
        db = self._SessionLocal()
        db.add(
            Photo(
                id=101,
                project_id=1,
                file_path=str(photo_path),
                file_name=photo_path.name,
                status="quarantined",
                deleted_at=datetime.now(),
            )
        )
        db.commit()

        with patch(
            "app.services.scanner._prepare_scan_file_with_retries"
        ) as prepare_mock, patch(
            "app.services.scanner.cleanup_missing_project_photos"
        ), patch(
            "app.services.folder_service.recompute_project_folder_counts"
        ):
            state = scan_project(db, 1)

        prepare_mock.assert_not_called()
        self.assertEqual(state["scanned"], 1)
        self.assertEqual(state["discovered_count"], 1)
        self.assertEqual(state["inserted"], 0)
        self.assertEqual(state["errors"], 0)
        self.assertEqual(
            db.query(Photo).filter(Photo.file_path == str(photo_path)).count(),
            1,
        )
        db.close()

    def test_scan_project_preserves_successful_writes_after_unique_violation(self) -> None:
        self._create_files(["a.jpg", "b.jpg", "c.jpg"])
        db = self._SessionLocal()
        conflict_path = self._library / "existing.jpg"
        db.add(
            Photo(
                id=500,
                project_id=1,
                file_path=str(conflict_path),
                file_name=conflict_path.name,
                status="pending",
            )
        )
        db.commit()
        persist_calls = 0

        def fake_prepare(file_path, **kwargs):
            return PreparedScanFile(
                path=file_path,
                path_str=str(file_path),
                relative_path=file_path.name,
                folder_path=None,
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
            nonlocal persist_calls
            persist_calls += 1
            if persist_calls == 2:
                session.add(
                    Photo(
                        id=100 + persist_calls,
                        project_id=project_id,
                        file_path=str(conflict_path),
                        file_name=conflict_path.name,
                        status="pending",
                    )
                )
                session.flush()
                return
            session.add(
                Photo(
                    id=100 + persist_calls,
                    project_id=project_id,
                    file_path=prepared.path_str,
                    file_name=prepared.path.name,
                    status="pending",
                )
            )
            session.flush()
            state["inserted"] += 1

        with patch(
            "app.services.scanner._prepare_scan_file_with_retries",
            side_effect=fake_prepare,
        ), patch(
            "app.services.scanner._persist_prepared_file",
            side_effect=fake_persist,
        ), patch(
            "app.services.scanner.cleanup_missing_project_photos"
        ), patch(
            "app.services.scanner.settings.scan_thumbnail_concurrency",
            1,
        ), patch(
            "app.services.scanner.settings.scan_queue_max_size",
            1,
        ), patch(
            "app.services.scanner.settings.scan_db_write_batch_size",
            20,
        ), patch(
            "app.services.folder_service.recompute_project_folder_counts"
        ):
            state = scan_project(db, 1)

        persisted_names = {
            photo.file_name
            for photo in db.query(Photo).filter(Photo.id.in_([101, 103])).all()
        }
        self.assertEqual(persist_calls, 3)
        self.assertEqual(len(persisted_names), 2)
        self.assertEqual(state["inserted"], 2)
        self.assertEqual(state["errors"], 1)
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
