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
from app.services.project_task_app_service import (  # noqa: E402
    ProjectTaskAppService,
    ProjectTaskRunContext,
)
from app.services.project_task_service import (  # noqa: E402
    TASK_TYPE_FACE_SCAN_PROJECT,
    TASK_TYPE_FACE_REMATCH_UNKNOWN,
    TASK_TYPE_LIBRARY_REINDEX,
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
    build_scan_status,
    enqueue_face_cluster_task,
    enqueue_scan_task,
    extract_task_failures,
    list_project_task_failures,
    request_project_task_cancel,
    request_project_task_cancel_by_id,
    request_project_task_pause,
    resume_project_task,
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
            "app.services.project_task_handlers.scan_project",
            side_effect=fake_scan,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["message"], "done")
        self.assertEqual(task.result_payload["scanned"], 12)
        self.assertEqual(task.result_payload["recent_files"][0]["status"], "success")
        db.close()

    def test_build_scan_status_includes_task_id(self) -> None:
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

        status = build_scan_status(task)

        self.assertEqual(status.task_id, task.id)
        self.assertTrue(status.running)
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
            "app.services.project_task_handlers.scan_project",
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

    def test_process_scan_task_marks_completed_with_errors_on_fail_fast_config(self) -> None:
        db = self._SessionLocal()
        project = db.query(Project).filter(Project.id == 1).first()
        assert project is not None
        project.photo_library_path = "/tmp/nonexistent-photo-library"
        project.thumbnail_path = ""
        db.commit()

        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="queued",
            request_params={},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "completed_with_errors")
        self.assertGreaterEqual(int(task.progress_payload.get("errors") or 0), 1)
        self.assertIn("Directory not found", str(task.progress_payload.get("message") or ""))
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
            "app.services.project_task_handlers.reindex_project",
            side_effect=RuntimeError("boom"),
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "failed")
        self.assertIn("boom", task.error_message or "")
        self.assertGreaterEqual(task.progress_payload["errors"], 1)
        db.close()

    def test_process_task_uses_injected_handler_registry(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type="custom_test_task",
            status="queued",
            request_params={},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        class _CustomHandler:
            def run(self, task: ProjectTask, context: ProjectTaskRunContext) -> dict:
                context.persist_progress(
                    task.id,
                    {
                        "running": True,
                        "errors": 0,
                        "message": "custom-running",
                    },
                )
                return {
                    "running": False,
                    "errors": 0,
                    "message": "custom-done",
                }

        ProjectTaskAppService(
            db,
            session_factory=self._SessionLocal,
            handlers={"custom_test_task": _CustomHandler()},
        ).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["message"], "custom-done")
        self.assertEqual(task.result_payload["message"], "custom-done")
        db.close()

    def test_cancel_queued_scan_task_marks_cancelled(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="queued",
            request_params={},
        )
        db.add(task)
        db.commit()

        cancelled = request_project_task_cancel(
            db,
            project_id=1,
            task_types=(TASK_TYPE_LIBRARY_SCAN, TASK_TYPE_LIBRARY_REINDEX),
        )

        self.assertIsNotNone(cancelled)
        assert cancelled is not None
        self.assertEqual(cancelled.status, "cancelled")
        self.assertFalse(cancelled.progress_payload["running"])
        self.assertEqual(cancelled.progress_payload["message"], "cancelled")
        db.close()

    def test_process_scan_task_honors_cancel_request_from_progress_callback(self) -> None:
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
        task_id = task.id

        def fake_scan(session, project_id, progress_callback=None):
            request_db = self._SessionLocal()
            active = request_db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
            assert active is not None
            progress = dict(active.progress_payload or {})
            progress["cancel_requested"] = True
            active.progress_payload = progress
            request_db.commit()
            request_db.close()

            if progress_callback is not None:
                progress_callback(
                    {
                        "running": True,
                        "scanned": 1,
                        "inserted": 0,
                        "updated": 0,
                        "errors": 0,
                        "current_path": "/tmp/a/test.jpg",
                        "message": "scanning",
                        "recent_errors": [],
                        "recent_files": [],
                    }
                )
            raise AssertionError("cancelled task should not continue after progress callback")

        with patch(
            "app.services.project_task_handlers.scan_project",
            side_effect=fake_scan,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "cancelled")
        self.assertFalse(task.progress_payload["running"])
        self.assertTrue(task.progress_payload["cancel_requested"])
        self.assertEqual(task.result_payload["message"], "cancelled")
        db.close()

    def test_pause_and_resume_queued_scan_task(self) -> None:
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

        paused = request_project_task_pause(db, project_id=1, task_id=task.id)
        assert paused is not None
        self.assertEqual(paused.status, "paused")
        self.assertFalse(paused.progress_payload["running"])
        self.assertEqual(paused.progress_payload["message"], "paused")

        resumed = resume_project_task(db, project_id=1, task_id=task.id)
        assert resumed is not None
        self.assertEqual(resumed.status, "queued")
        self.assertTrue(resumed.progress_payload["running"])
        self.assertNotIn("pause_requested", resumed.progress_payload)
        db.close()

    def test_cancel_paused_scan_task_marks_cancelled_immediately(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="paused",
            request_params={},
            progress_payload={
                "running": False,
                "pause_requested": True,
                "message": "paused",
            },
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        cancelled = request_project_task_cancel_by_id(db, project_id=1, task_id=task.id)

        assert cancelled is not None
        self.assertEqual(cancelled.status, "cancelled")
        self.assertFalse(cancelled.progress_payload["running"])
        self.assertTrue(cancelled.progress_payload["cancel_requested"])
        self.assertNotIn("pause_requested", cancelled.progress_payload)
        self.assertEqual(cancelled.progress_payload["message"], "cancelled")
        self.assertEqual(cancelled.result_payload["message"], "cancelled")
        db.close()

    def test_extract_task_failures_normalizes_recent_files_and_errors(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="completed_with_errors",
            request_params={},
            progress_payload={
                "recent_errors": ["alpha failure", "beta failure"],
                "recent_files": [
                    {
                        "path": "/tmp/a/ok.jpg",
                        "status": "success",
                        "message": None,
                        "timestamp": "2026-01-01T00:00:00+00:00",
                    },
                    {
                        "path": "/tmp/a/bad.jpg",
                        "status": "failed",
                        "message": "decode failed",
                        "timestamp": "2026-01-01T00:01:00+00:00",
                    },
                ],
            },
            result_payload={
                "recent_errors": ["beta failure"],
                "recent_files": [
                    {
                        "path": "/tmp/a/bad.jpg",
                        "status": "failed",
                        "message": "decode failed",
                        "timestamp": "2026-01-01T00:01:00+00:00",
                    }
                ],
            },
            error_message="terminal failure",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        failures = extract_task_failures(task)

        self.assertEqual(len(failures), 4)
        self.assertEqual(failures[0]["source"], "task_error")
        self.assertEqual(failures[0]["message"], "terminal failure")
        self.assertEqual(failures[1]["source"], "file_progress")
        self.assertEqual(failures[1]["path"], "/tmp/a/bad.jpg")
        self.assertEqual(failures[2]["source"], "recent_error")
        self.assertEqual(failures[2]["message"], "beta failure")
        self.assertEqual(failures[3]["source"], "recent_error")
        self.assertEqual(failures[3]["message"], "alpha failure")
        db.close()

    def test_list_project_task_failures_supports_pagination(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_LIBRARY_SCAN,
            status="failed",
            request_params={},
            progress_payload={
                "recent_errors": ["first failure", "second failure", "third failure"],
                "recent_files": [],
            },
            error_message=None,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        result = list_project_task_failures(db, project_id=1, task_id=task.id, limit=2, offset=1)

        assert result is not None
        total, items = result
        self.assertEqual(total, 3)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["message"], "second failure")
        self.assertEqual(items[1]["message"], "first failure")
        db.close()

    def test_process_scan_task_honors_pause_request_from_progress_callback(self) -> None:
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
        task_id = task.id

        def fake_scan(session, project_id, progress_callback=None):
            request_db = self._SessionLocal()
            active = request_db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
            assert active is not None
            progress = dict(active.progress_payload or {})
            progress["pause_requested"] = True
            active.progress_payload = progress
            request_db.commit()
            request_db.close()

            if progress_callback is not None:
                progress_callback(
                    {
                        "running": True,
                        "scanned": 1,
                        "inserted": 0,
                        "updated": 0,
                        "errors": 0,
                        "current_path": "/tmp/a/test.jpg",
                        "message": "scanning",
                        "recent_errors": [],
                        "recent_files": [],
                    }
                )
            raise AssertionError("paused task should not continue after progress callback")

        with patch(
            "app.services.project_task_handlers.scan_project",
            side_effect=fake_scan,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "paused")
        self.assertFalse(task.progress_payload["running"])
        self.assertTrue(task.progress_payload["pause_requested"])
        self.assertEqual(task.result_payload["message"], "paused")
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
            "app.services.project_task_handlers.cluster_unknown_faces",
            return_value=_Result(),
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["clusters_created"], 4)
        self.assertEqual(task.progress_payload["max_faces"], 123)
        self.assertEqual(task.result_payload["faces_clustered"], 21)
        db.close()

    def test_process_unknown_face_cluster_task_honors_cancel_callback(self) -> None:
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
        task_id = task.id

        def fake_cluster(session, *, project_id, max_faces, progress_callback=None):
            request_db = self._SessionLocal()
            active = request_db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
            assert active is not None
            progress = dict(active.progress_payload or {})
            progress["cancel_requested"] = True
            active.progress_payload = progress
            request_db.commit()
            request_db.close()

            if progress_callback is not None:
                progress_callback(
                    {
                        "project_id": project_id,
                        "task_id": task_id,
                        "status": "running",
                        "running": True,
                        "max_faces": max_faces,
                        "clusters_created": 1,
                        "persons_created": 0,
                        "faces_clustered": 10,
                        "assignments_created": 0,
                        "errors": 0,
                        "recent_errors": [],
                        "message": "clustering unknown faces (10/123)",
                    }
                )
            raise AssertionError("cancelled cluster task should not continue")

        with patch(
            "app.services.project_task_handlers.cluster_unknown_faces",
            side_effect=fake_cluster,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "cancelled")
        self.assertFalse(task.progress_payload["running"])
        self.assertEqual(task.result_payload["message"], "cancelled")
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
            "app.services.project_task_handlers.FaceScanBatchService",
            _FakeFaceScanBatchService,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["created_jobs"], 2)
        self.assertEqual(task.progress_payload["candidate_count"], 2)
        self.assertEqual(task.result_payload["message"], "Project face scan jobs queued")
        db.close()

    def test_process_face_rematch_unknown_task_marks_success(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_FACE_REMATCH_UNKNOWN,
            status="queued",
            request_params={"max_faces": 321},
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        class _Result:
            faces_considered = 9
            matched_faces = 5
            auto_assigned = 2
            review_pending = 3

        with patch(
            "app.services.project_task_handlers.rematch_unknown_faces",
            return_value=_Result(),
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "success")
        self.assertEqual(task.progress_payload["max_faces"], 321)
        self.assertEqual(task.progress_payload["faces_considered"], 9)
        self.assertEqual(task.result_payload["matched_faces"], 5)
        self.assertEqual(task.result_payload["review_pending"], 3)
        db.close()

    def test_process_face_rematch_unknown_task_honors_cancel_callback(self) -> None:
        db = self._SessionLocal()
        task = ProjectTask(
            project_id=1,
            task_type=TASK_TYPE_FACE_REMATCH_UNKNOWN,
            status="queued",
            request_params={"max_faces": 321},
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

        def fake_rematch(
            session,
            *,
            project_id,
            max_faces,
            scope="unknown",
            person_id=None,
            start_time=None,
            end_time=None,
            progress_callback=None,
        ):
            request_db = self._SessionLocal()
            active = request_db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
            assert active is not None
            progress = dict(active.progress_payload or {})
            progress["cancel_requested"] = True
            active.progress_payload = progress
            request_db.commit()
            request_db.close()

            if progress_callback is not None:
                progress_callback(
                    {
                        "project_id": project_id,
                        "task_id": task_id,
                        "status": "running",
                        "running": True,
                        "max_faces": max_faces,
                        "scope": scope,
                        "person_id": person_id,
                        "start_time": start_time.isoformat() if start_time else None,
                        "end_time": end_time.isoformat() if end_time else None,
                        "faces_considered": 25,
                        "matched_faces": 9,
                        "auto_assigned": 3,
                        "review_pending": 6,
                        "errors": 0,
                        "recent_errors": [],
                        "message": "rematching unknown faces (25/321)",
                    }
                )
            raise AssertionError("cancelled rematch task should not continue")

        with patch(
            "app.services.project_task_handlers.rematch_unknown_faces",
            side_effect=fake_rematch,
        ):
            ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)

        db.refresh(task)
        self.assertEqual(task.status, "cancelled")
        self.assertFalse(task.progress_payload["running"])
        self.assertEqual(task.result_payload["message"], "cancelled")
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
