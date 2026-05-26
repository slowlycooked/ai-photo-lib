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
    TASK_TYPE_LIBRARY_REINDEX,
    TASK_TYPE_LIBRARY_SCAN,
    TASK_TYPE_UNKNOWN_FACE_CLUSTERING,
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
