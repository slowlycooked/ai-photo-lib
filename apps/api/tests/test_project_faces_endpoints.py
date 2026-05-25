from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Generator

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


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

CREATE TABLE face_detections (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  bbox_x INTEGER NOT NULL,
  bbox_y INTEGER NOT NULL,
  bbox_w INTEGER NOT NULL,
  bbox_h INTEGER NOT NULL,
  detection_confidence REAL,
  face_quality_score REAL,
  face_crop_path TEXT,
  face_crop_hash TEXT,
  status TEXT NOT NULL DEFAULT 'embedded',
  error_message TEXT,
  detected_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE face_embeddings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  face_detection_id INTEGER NOT NULL,
  model_provider TEXT,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT '',
  embedding_dim INTEGER NOT NULL,
  embedding_vector TEXT,
  embedding_hash TEXT,
  embedded_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_face_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
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

CREATE TABLE ai_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id INTEGER NOT NULL,
  project_id INTEGER NOT NULL,
  job_type TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT,
  prompt_template_id INTEGER,
  prompt_version INTEGER,
  model_name TEXT,
  model_params TEXT,
  raw_model_output TEXT,
  parse_error TEXT,
  started_at TEXT,
  finished_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO photos (id, project_id, file_path, file_name, status)
VALUES (101, 1, '/tmp/a/a.jpg', 'a.jpg', 'indexed'),
       (202, 2, '/tmp/b/b.jpg', 'b.jpg', 'indexed');

INSERT INTO face_detections (
  id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, status
) VALUES
  (301, 1, 101, 10, 10, 20, 20, 'embedded'),
  (401, 2, 202, 15, 15, 25, 25, 'embedded');

INSERT INTO face_embeddings (
  id, project_id, face_detection_id, model_name, model_version, embedding_dim
) VALUES
  (501, 1, 301, 'fake-sface', 'v1', 3),
  (601, 2, 401, 'fake-sface', 'v1', 3);

INSERT INTO project_face_settings (
  id, project_id, face_recognition_enabled, face_embedding_model
) VALUES
  (1, 1, 1, 'fake-sface'),
  (2, 2, 1, 'fake-sface');
"""


class ProjectFacesEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._engine = sa.create_engine(
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
            for stmt in [part.strip() for part in SEED_SQL.split(";") if part.strip()]:
                conn.execute(sa.text(stmt))

        def override_get_db() -> Generator[Session, None, None]:
            db = self._SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_project_cannot_read_other_project_face(self) -> None:
        res = self.client.get("/projects/1/faces/401")
        self.assertEqual(res.status_code, 404)

    def test_project_can_read_own_face(self) -> None:
        res = self.client.get("/projects/1/faces/301")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["id"], 301)
        self.assertEqual(body["project_id"], 1)
        self.assertEqual(len(body["embeddings"]), 1)

    def test_project_faces_list_is_scoped(self) -> None:
        res = self.client.get("/projects/1/faces")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["id"], 301)

    def test_project_face_scan_jobs_can_be_enqueued_and_counted(self) -> None:
      start = self.client.post("/projects/1/face-scan-project/start")
      self.assertEqual(start.status_code, 200)
      payload = start.json()
      self.assertEqual(payload["project_id"], 1)
      self.assertEqual(payload["created_jobs"], 1)
      self.assertEqual(payload["skipped_active_jobs"], 0)

      status = self.client.get("/projects/1/face-scan-project/status")
      self.assertEqual(status.status_code, 200)
      status_payload = status.json()
      self.assertEqual(status_payload["queued"], 1)
      self.assertEqual(status_payload["total"], 1)

      start_again = self.client.post("/projects/1/face-scan-project/start")
      self.assertEqual(start_again.status_code, 200)
      payload_again = start_again.json()
      self.assertEqual(payload_again["created_jobs"], 0)
      self.assertEqual(payload_again["skipped_active_jobs"], 1)
