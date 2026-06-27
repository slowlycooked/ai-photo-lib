from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.models.face import ProjectFaceSettings  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.models.project_task import ProjectTask  # noqa: E402
from app.services.face_auto_rematch_scheduler import FaceAutoRematchScheduler  # noqa: E402


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

CREATE TABLE project_face_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  face_recognition_enabled BOOLEAN NOT NULL DEFAULT 0,
  face_provider TEXT NOT NULL DEFAULT 'opencv',
  face_detector_model TEXT NOT NULL DEFAULT 'yunet',
  face_embedding_model TEXT NOT NULL DEFAULT 'sface',
  face_runtime TEXT NOT NULL DEFAULT 'cpu',
  store_face_crops BOOLEAN NOT NULL DEFAULT 1,
  face_crop_storage TEXT NOT NULL DEFAULT 'local',
  auto_accept_threshold REAL NOT NULL DEFAULT 0.62,
  review_threshold REAL NOT NULL DEFAULT 0.48,
  cluster_threshold REAL NOT NULL DEFAULT 0.50,
  min_face_size INTEGER NOT NULL DEFAULT 40,
  min_detection_confidence REAL NOT NULL DEFAULT 0.75,
  min_quality_for_prototype REAL NOT NULL DEFAULT 0.70,
  max_positive_samples_per_person INTEGER NOT NULL DEFAULT 200,
  allow_auto_assignment BOOLEAN NOT NULL DEFAULT 1,
  require_human_confirmation_for_new_person BOOLEAN NOT NULL DEFAULT 1,
  enable_negative_constraints BOOLEAN NOT NULL DEFAULT 1,
  enable_person_cannot_links BOOLEAN NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_tasks (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  retry_count INTEGER NOT NULL DEFAULT 0,
  request_params JSON,
  progress_payload JSON,
  result_payload JSON,
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
"""


class FaceAutoRematchSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
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
        with self._engine.begin() as conn:
            for stmt in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
                conn.execute(sa.text(stmt))

    def tearDown(self) -> None:
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def _seed_projects(self) -> None:
        db = self._SessionLocal()
        try:
            db.add_all(
                [
                    Project(
                        id=1,
                        name="Enabled",
                        description=None,
                        photo_library_path="/tmp/a",
                        thumbnail_path="/tmp/thumbs-a",
                        is_default=True,
                    ),
                    Project(
                        id=2,
                        name="Disabled",
                        description=None,
                        photo_library_path="/tmp/b",
                        thumbnail_path="/tmp/thumbs-b",
                        is_default=False,
                    ),
                ]
            )
            db.add_all(
                [
                    ProjectFaceSettings(
                        id=1,
                        project_id=1,
                        face_recognition_enabled=True,
                    ),
                    ProjectFaceSettings(
                        id=2,
                        project_id=2,
                        face_recognition_enabled=False,
                    ),
                ]
            )
            db.commit()
        finally:
            db.close()

    def test_schedules_enabled_projects_once_per_daily_window(self) -> None:
        self._seed_projects()
        db = self._SessionLocal()
        try:
            with (
                patch.object(settings, "face_auto_rematch_enabled", True),
                patch.object(settings, "face_auto_rematch_schedule", "daily"),
                patch.object(settings, "face_auto_rematch_max_faces", 1234),
            ):
                first = FaceAutoRematchScheduler(db).run_once()
                second = FaceAutoRematchScheduler(db).run_once()

            self.assertEqual(first.projects_checked, 1)
            self.assertEqual(first.tasks_created, 1)
            self.assertEqual(second.tasks_created, 0)
            self.assertEqual(second.skipped_recent, 1)

            tasks = db.query(ProjectTask).all()
            self.assertEqual(len(tasks), 1)
            self.assertEqual(tasks[0].project_id, 1)
            self.assertEqual(tasks[0].task_type, "face_rematch_unknown")
            self.assertEqual(tasks[0].request_params["trigger"], "scheduled_auto_rematch")
            self.assertEqual(tasks[0].request_params["schedule"], "daily")
            self.assertEqual(tasks[0].request_params["max_faces"], 1234)
        finally:
            db.close()

    def test_disabled_scheduler_does_not_enqueue(self) -> None:
        self._seed_projects()
        db = self._SessionLocal()
        try:
            with patch.object(settings, "face_auto_rematch_enabled", False):
                result = FaceAutoRematchScheduler(db).run_once()

            self.assertEqual(result.skipped_disabled, 1)
            self.assertEqual(db.query(ProjectTask).count(), 0)
        finally:
            db.close()
