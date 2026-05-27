from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.project_task import ProjectTask  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.project_task_app_service import ProjectTaskAppService  # noqa: E402
from app.services.project_task_service import (  # noqa: E402
    TASK_TYPE_FACE_SCAN_PROJECT,
    TASK_TYPE_LIBRARY_REINDEX,
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
    enqueue_face_cluster_task,
    enqueue_scan_task,
)


class ProjectTaskAppServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        from sqlalchemy import create_engine

        self._engine = create_engine(
            f"sqlite:///{self._tmp.name}",
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
        ProjectTask.__table__.create(self._engine)

        db = self._SessionLocal()
        db.add(
            Project(
                id=1,
                name="Project A",
                description=None,
                photo_library_path="/tmp/a",
                thumbnail_path="/tmp/thumbs",
                is_default=True,
            )
        )
        db.commit()
        db.close()

    def tearDown(self) -> None:
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_process_scan_task_marks_success_and_persists_progress(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="queued",
            request_params={},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        def fake_scan(session, project_id, progress_callback=None):
            if progress_callback is not None:
                progress_callback(
                    {
                        "running": True,
                        "scanned": 12,
                        "inserted": 2,
                        "updated": 4,
                        "errors": 0,
                        "current_path": "/tmp/a/test.jpg",
                        "message": "scanning",
                        "recent_errors": [],
                        "recent_files": [
                            {
                                "path": "/tmp/a/test.jpg",
                                "status": "success",
                                "message": None,
                                "timestamp": "2026-01-01T00:00:00+00:00",
                            }
                        ],
                    }
                )
            return {
                "running": False,
                "scanned": 12,
                "inserted": 2,
                "updated": 4,
                "errors": 0,
                "current_path": None,
                "message": "done",
                "recent_errors": [],
                "recent_files": [
                    {
                        "path": "/tmp/a/test.jpg",
                        "status": "success",
                        "message": None,
                        "timestamp": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }

        with patch(
            "app.services.project_task_app_service.scan_project",
            side_effect=fake_scan,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["message"], "done")
        self.assertEqual(task.result_payload["scanned"], 12)
        self.assertEqual(task.result_payload["recent_files"][0]["status"], "success")
        db.close()

    def test_process_scan_task_preserves_completed_with_errors_payload(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="queued",
            request_params={},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        def fake_scan(session, project_id, progress_callback=None):
            return {
                "running": False,
                "scanned": 12,
                "inserted": 2,
                "updated": 4,
                "errors": 1,
                "current_path": None,
                "message": "done_with_errors",
                "recent_errors": ["bad.jpg: decode failed"],
                "recent_files": [
                    {
                        "path": "/tmp/a/bad.jpg",
                        "status": "failed",
                        "message": "decode failed",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }

        with patch(
            "app.services.project_task_app_service.scan_project",
            side_effect=fake_scan,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "completed_with_errors")
        self.assertEqual(task.progress_payload["message"], "done_with_errors")
        self.assertEqual(task.progress_payload["errors"], 1)
        self.assertEqual(task.result_payload["recent_errors"], ["bad.jpg: decode failed"])
        self.assertEqual(task.result_payload["recent_files"][0]["status"], "failed")
        db.close()

    def test_process_reindex_task_marks_failure(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_REINDEX,
            status="queued",
            request_params={"scope": "all"},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        with patch(
            "app.services.project_task_app_service.reindex_project",
            side_effect=RuntimeError("boom"),
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "failed")
        self.assertIn("boom", task.error_message or "")
        self.assertGreaterEqual(task.progress_payload["errors"], 1)
        db.close()

    def test_process_unknown_face_cluster_task_marks_success(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
            status="queued",
            request_params={"max_faces": 123},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        class _Result:
            clusters_created = 4
            persons_created = 4
            faces_clustered = 21
            assignments_created = 21

        with patch(
            "app.services.project_task_app_service.cluster_unknown_faces",
            return_value=_Result(),
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["clusters_created"], 4)
        self.assertEqual(task.progress_payload["max_faces"], 123)
        self.assertEqual(task.result_payload["faces_clustered"], 21)
        db.close()

    def test_process_face_scan_project_task_queues_child_jobs(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_FACE_SCAN_PROJECT,
            status="queued",
            request_params={
                "scope": "missing",
                "photo_ids": [101, 102],
                "candidate_count": 2,
                "total_photos": 3,
            },
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        class _Plan:
            project_id = 1
            candidate_photo_ids = [101, 102]
            skipped_active = 0

        class _EnqueueResult:
            created_jobs = 2
            skipped_active = 0

        class _FakeFaceScanBatchService:
            def __init__(self, session) -> None:
                self.session = session

            def plan(self, project_id, *, scope, photo_ids, force):
                assert project_id == 1
                assert scope == "missing"
                assert photo_ids == [101, 102]
                assert force is False
                return _Plan()

            def enqueue(self, plan):
                assert plan.candidate_photo_ids == [101, 102]
                return _EnqueueResult()

        with patch(
            "app.services.project_task_app_service.FaceScanBatchService",
            _FakeFaceScanBatchService,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["created_jobs"], 2)
        self.assertEqual(task.progress_payload["candidate_count"], 2)
        self.assertEqual(task.result_payload["message"], "Project face scan jobs queued")
        db.close()

    def test_enqueue_scan_task_returns_existing_active_scan_family_task(self) -> None:
        db = self._SessionLocal()

        first = enqueue_scan_task(
            db,
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            request_params={},
        )
        second = enqueue_scan_task(
            db,
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_REINDEX,
            request_params={"scope": "all"},
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(second.task.id, first.task.id)
        self.assertEqual(db.query(ProjectTask).count(), 1)
        db.close()

    def test_enqueue_face_cluster_task_is_independent_from_scan_family(self) -> None:
        db = self._SessionLocal()

        scan = enqueue_scan_task(
            db,
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            request_params={},
        )
        cluster = enqueue_face_cluster_task(db, project_id=1, max_faces=200)
        duplicate_cluster = enqueue_face_cluster_task(db, project_id=1, max_faces=300)

        self.assertTrue(scan.created)
        self.assertTrue(cluster.created)
        self.assertFalse(duplicate_cluster.created)
        self.assertEqual(duplicate_cluster.task.id, cluster.task.id)
        self.assertEqual(db.query(ProjectTask).count(), 2)
        db.close()
