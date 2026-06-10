from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

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
from app.models.project_task import ProjectTask  # noqa: E402
from app.services.face_scan_service import FaceScanResult  # noqa: E402
from app.services.project_task_app_service import ProjectTaskAppService  # noqa: E402
from app.services.unknown_face_clustering_service import UnknownFaceClusteringResult  # noqa: E402


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

CREATE TABLE photo_derivatives (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  path TEXT,
  format TEXT,
  width INTEGER,
  height INTEGER,
  source_path TEXT,
  source_mtime REAL,
  source_hash TEXT,
  quality INTEGER,
  status TEXT NOT NULL DEFAULT 'ready',
  error_message TEXT,
  face_detection_id INTEGER,
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
  locked_by TEXT,
  locked_at TEXT,
  heartbeat_at TEXT,
  lease_expires_at TEXT,
  last_error_code TEXT,
  last_error_at TEXT,
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
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO photos (id, project_id, file_path, file_name, status)
VALUES (101, 1, '/tmp/a/a.jpg', 'a.jpg', 'indexed'),
  (102, 1, '/tmp/a/cat.jpg', 'cat.jpg', 'indexed'),
  (103, 1, '/tmp/a/dog.jpg', 'dog.jpg', 'indexed'),
       (202, 2, '/tmp/b/b.jpg', 'b.jpg', 'indexed');

INSERT INTO face_detections (
  id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, status
) VALUES
  (301, 1, 101, 10, 10, 20, 20, 'embedded'),
  (302, 1, 102, 15, 15, 25, 25, 'embedded'),
  (401, 2, 202, 15, 15, 25, 25, 'embedded');

INSERT INTO face_embeddings (
  id, project_id, face_detection_id, model_name, model_version, embedding_dim
) VALUES
  (501, 1, 301, 'fake-sface', 'v1', 3),
  (502, 1, 302, 'fake-sface', 'v1', 3),
  (601, 2, 401, 'fake-sface', 'v1', 3);

INSERT INTO photo_derivatives (
  id, project_id, photo_id, kind, path, source_path, source_mtime, status
) VALUES
  (701, 1, 102, 'face_work_image', '/tmp/a/face-work-102.jpg', '/tmp/a/cat.jpg', 1.0, 'ready');

INSERT INTO ai_jobs (
  id, photo_id, project_id, job_type, status
) VALUES
  (901, 103, 1, 'face_scan', 'failed');

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
    self._created_files = [
      Path("/tmp/a/a.jpg"),
      Path("/tmp/a/cat.jpg"),
      Path("/tmp/a/face-work-102.jpg"),
      Path("/tmp/a/dog.jpg"),
      Path("/tmp/b/b.jpg"),
    ]
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
      conn.execute(
        sa.text(
          """
          UPDATE face_detections
          SET updated_at = '2024-01-01 00:00:00'
          WHERE id = 302
          """
        )
      )

    for file_path in self._created_files:
      file_path.parent.mkdir(parents=True, exist_ok=True)
      file_path.write_bytes(b"test")

    for file_path in [Path("/tmp/a/cat.jpg"), Path("/tmp/a/face-work-102.jpg")]:
      os.utime(file_path, (1, 1))

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
    for file_path in self._created_files:
      if file_path.exists():
        file_path.unlink()
    for directory in (Path("/tmp/a"), Path("/tmp/b")):
      if directory.exists():
        try:
          directory.rmdir()
        except OSError:
          pass

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

  def test_manual_face_scan_creates_face_scan_job_record(self) -> None:
    with patch("app.routers.project_faces.FaceScanService.scan_photo") as mock_scan, patch(
      "app.routers.project_faces.cluster_unknown_faces"
    ) as mock_cluster:
      mock_scan.return_value = FaceScanResult(
        project_id=1,
        photo_id=101,
        provider="opencv",
        detector_model="yunet",
        embedding_model="fake-sface",
        faces_detected=2,
        detections_created=1,
        detections_updated=1,
        embeddings_created=1,
        embeddings_updated=1,
        auto_assigned=1,
        review_pending=0,
        failures=0,
        message="Face scan completed",
        scan_source="face_work_image",
        scan_quality_degraded=False,
      )
      mock_cluster.return_value = UnknownFaceClusteringResult(
        project_id=1,
        clusters_created=1,
        persons_created=1,
        faces_clustered=2,
        assignments_created=2,
      )

      res = self.client.post("/projects/1/photos/101/face-scan")

    self.assertEqual(res.status_code, 200)
    payload = res.json()
    self.assertEqual(payload["photo_id"], 101)
    self.assertEqual(payload["faces_detected"], 2)
    self.assertEqual(payload["review_pending"], 2)

    with self._engine.begin() as conn:
      row = conn.execute(
        sa.text(
          """
          SELECT status, job_type, photo_id, project_id, raw_model_output
          FROM ai_jobs
          WHERE project_id = 1 AND photo_id = 101 AND job_type = 'face_scan'
          ORDER BY id DESC
          LIMIT 1
          """
        )
      ).fetchone()

    self.assertIsNotNone(row)
    assert row is not None
    self.assertEqual(row[0], "success")
    self.assertEqual(row[1], "face_scan")
    self.assertEqual(row[2], 101)
    self.assertEqual(row[3], 1)
    self.assertIn('"faces_detected": 2', row[4])
    self.assertIn('"review_pending": 2', row[4])

  def test_manual_face_scan_triggers_unknown_clustering_for_current_photo(self) -> None:
    with patch("app.routers.project_faces.FaceScanService.scan_photo") as mock_scan, patch(
      "app.routers.project_faces.cluster_unknown_faces"
    ) as mock_cluster:
      mock_scan.return_value = FaceScanResult(
        project_id=1,
        photo_id=101,
        provider="opencv",
        detector_model="yunet",
        embedding_model="fake-sface",
        faces_detected=2,
        detections_created=1,
        detections_updated=1,
        embeddings_created=1,
        embeddings_updated=1,
        auto_assigned=0,
        review_pending=0,
        failures=0,
        message="Face scan completed",
        scan_source="face_work_image",
        scan_quality_degraded=False,
      )
      mock_cluster.return_value = UnknownFaceClusteringResult(
        project_id=1,
        clusters_created=1,
        persons_created=1,
        faces_clustered=2,
        assignments_created=2,
      )

      res = self.client.post("/projects/1/photos/101/face-scan")

    self.assertEqual(res.status_code, 200)
    mock_cluster.assert_called_once_with(
      unittest.mock.ANY,
      project_id=1,
      max_faces=2,
      photo_ids=[101],
    )

  def test_manual_face_scan_reports_reason_when_review_tables_missing(self) -> None:
    with patch("app.routers.project_faces.FaceScanService.scan_photo") as mock_scan, patch(
      "app.routers.project_faces.cluster_unknown_faces"
    ) as mock_cluster:
      mock_scan.return_value = FaceScanResult(
        project_id=1,
        photo_id=101,
        provider="opencv",
        detector_model="yunet",
        embedding_model="fake-sface",
        faces_detected=5,
        detections_created=5,
        detections_updated=0,
        embeddings_created=5,
        embeddings_updated=0,
        auto_assigned=0,
        review_pending=0,
        failures=0,
        message="Face scan completed",
        scan_source="face_work_image",
        scan_quality_degraded=False,
      )
      mock_cluster.return_value = UnknownFaceClusteringResult(
        project_id=1,
        clusters_created=0,
        persons_created=0,
        faces_clustered=0,
        assignments_created=0,
        skipped_reason="missing_people_tables",
      )

      res = self.client.post("/projects/1/photos/101/face-scan")

    self.assertEqual(res.status_code, 200)
    payload = res.json()
    self.assertEqual(payload["review_pending"], 0)
    self.assertIn("persons/person_face_assignments", payload["message"])
    self.assertIn("alembic upgrade head", payload["message"])

  def test_project_face_crop_missing_file_returns_404(self) -> None:
    with self._engine.begin() as conn:
      conn.execute(
        sa.text(
          """
          UPDATE face_detections
          SET face_crop_path = '/tmp/a/missing-face.jpg'
          WHERE id = 301
          """
        )
      )

    res = self.client.get("/projects/1/faces/301/crop")
    self.assertEqual(res.status_code, 404)

  def test_project_faces_list_is_scoped(self) -> None:
    res = self.client.get("/projects/1/faces")
    self.assertEqual(res.status_code, 200)
    body = res.json()
    self.assertEqual(body["total"], 2)
    self.assertEqual({item["id"] for item in body["items"]}, {301, 302})

  def test_project_face_scan_jobs_missing_scope_queues_unscanned_photos(self) -> None:
    start = self.client.post("/projects/1/face-scan-project/start")
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["project_id"], 1)
    self.assertEqual(payload["scope"], "missing")
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["task_status"], "queued")
    self.assertIsNotNone(payload["task_id"])
    self.assertEqual(payload["created_jobs"], 0)
    self.assertEqual(payload["skipped_active_jobs"], 0)

  def test_project_face_scan_jobs_selected_scope_queues_requested_photos(self) -> None:
    start = self.client.post(
      "/projects/1/face-scan-project/start",
      json={"scope": "selected", "photo_ids": [102, 103]},
    )
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["scope"], "selected")
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["created_jobs"], 0)
    self.assertEqual(payload["candidate_count"], 2)

  def test_project_face_scan_jobs_failed_scope_queues_failed_photos(self) -> None:
    start = self.client.post(
      "/projects/1/face-scan-project/start",
      json={"scope": "failed"},
    )
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["scope"], "failed")
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["created_jobs"], 0)
    self.assertEqual(payload["candidate_count"], 1)

  def test_project_face_scan_jobs_stale_scope_respects_updated_settings(self) -> None:
    settings_update = self.client.put(
      "/projects/1/face-settings",
      json={"store_face_crops": False},
    )
    self.assertEqual(settings_update.status_code, 200)

    start = self.client.post(
      "/projects/1/face-scan-project/start",
      json={"scope": "stale"},
    )
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["scope"], "stale")
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["created_jobs"], 0)
    self.assertEqual(payload["candidate_count"], 1)

  def test_project_face_scan_jobs_can_be_enqueued_and_counted(self) -> None:
    start = self.client.post("/projects/1/face-scan-project/start")
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["project_id"], 1)
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["created_jobs"], 0)
    self.assertEqual(payload["skipped_active_jobs"], 0)

    status = self.client.get("/projects/1/face-scan-project/status")
    self.assertEqual(status.status_code, 200)
    status_payload = status.json()
    self.assertEqual(status_payload["queued"], 1)
    self.assertEqual(status_payload["failed"], 1)
    self.assertEqual(status_payload["total"], 2)
    self.assertEqual(status_payload["task_status"], "queued")

    start_again = self.client.post("/projects/1/face-scan-project/start")
    self.assertEqual(start_again.status_code, 200)
    payload_again = start_again.json()
    self.assertEqual(payload_again["created_jobs"], 0)
    self.assertEqual(payload_again["task_created"], False)
    self.assertEqual(payload_again["skipped_active_jobs"], 1)

  def test_project_face_scan_jobs_dry_run_returns_plan_without_enqueue(self) -> None:
    start = self.client.post(
      "/projects/1/face-scan-project/start",
      json={"scope": "missing", "dry_run": True},
    )
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["scope"], "missing")
    self.assertTrue(payload["dry_run"])
    self.assertEqual(payload["candidate_count"], 1)
    self.assertEqual(payload["created_jobs"], 0)

    status = self.client.get("/projects/1/face-scan-project/status")
    self.assertEqual(status.status_code, 200)
    status_payload = status.json()
    self.assertEqual(status_payload["queued"], 0)
    self.assertEqual(status_payload["failed"], 1)

  def test_face_rematch_unknown_can_be_queued_and_reported(self) -> None:
    start = self.client.post("/projects/1/face-rematch-unknown", json={"max_faces": 123})
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["status"]["status"], "queued")
    self.assertEqual(payload["status"]["max_faces"], 123)
    self.assertEqual(payload["status"]["scope"], "unknown")
    self.assertTrue(payload["status"]["running"])

    duplicate = self.client.post("/projects/1/face-rematch-unknown", json={"max_faces": 456})
    self.assertEqual(duplicate.status_code, 200)
    duplicate_payload = duplicate.json()
    self.assertEqual(duplicate_payload["message"], "Unknown face rematch already in progress")
    self.assertEqual(duplicate_payload["status"]["max_faces"], 123)

    status = self.client.get("/projects/1/face-rematch-unknown/status")
    self.assertEqual(status.status_code, 200)
    status_payload = status.json()
    self.assertEqual(status_payload["status"], "queued")
    self.assertEqual(status_payload["max_faces"], 123)
    self.assertEqual(status_payload["scope"], "unknown")

  def test_face_rematch_unknown_supports_person_scope(self) -> None:
    start = self.client.post(
      "/projects/1/face-rematch-unknown",
      json={"max_faces": 88, "scope": "person", "person_id": 101},
    )
    self.assertEqual(start.status_code, 200)
    payload = start.json()
    self.assertEqual(payload["status"]["scope"], "person")
    self.assertEqual(payload["status"]["person_id"], 101)

  def test_face_rematch_unknown_time_range_requires_valid_window(self) -> None:
    missing = self.client.post(
      "/projects/1/face-rematch-unknown",
      json={"scope": "time_range", "max_faces": 100},
    )
    self.assertEqual(missing.status_code, 422)

    invalid = self.client.post(
      "/projects/1/face-rematch-unknown",
      json={
        "scope": "time_range",
        "start_time": "2026-05-30T00:00:00Z",
        "end_time": "2026-05-29T00:00:00Z",
      },
    )
    self.assertEqual(invalid.status_code, 422)

  def test_project_tasks_can_be_listed_and_read_with_recent_errors(self) -> None:
    with self._engine.begin() as conn:
      conn.execute(
        sa.text(
          """
          INSERT INTO project_tasks (
            id, project_id, task_type, status, retry_count,
            request_params, progress_payload, result_payload, error_message
          )
          VALUES (
            3001, 1, 'library_scan', 'failed', 1,
            '{"scope":"all"}',
            '{"recent_errors":["bad.jpg: decode failed"],"message":"failed"}',
            NULL,
            'scan exploded'
          ),
          (
            3002, 2, 'library_scan', 'failed', 1,
            '{}',
            '{"recent_errors":["other project"],"message":"failed"}',
            NULL,
            'hidden'
          )
          """
        )
      )

    listed = self.client.get("/projects/1/tasks?status=failed&limit=10")
    self.assertEqual(listed.status_code, 200)
    payload = listed.json()
    self.assertEqual(payload["total"], 1)
    self.assertEqual(payload["items"][0]["id"], 3001)
    self.assertEqual(payload["items"][0]["task_type"], "library_scan")
    self.assertEqual(
      payload["items"][0]["recent_errors"],
      ["bad.jpg: decode failed", "scan exploded"],
    )

    detail = self.client.get("/projects/1/tasks/3001")
    self.assertEqual(detail.status_code, 200)
    self.assertEqual(detail.json()["request_params"], {"scope": "all"})

    other_project = self.client.get("/projects/1/tasks/3002")
    self.assertEqual(other_project.status_code, 404)

  def test_project_task_can_be_paused_and_resumed(self) -> None:
    with self._engine.begin() as conn:
      conn.execute(
        sa.text(
          """
          INSERT INTO project_tasks (id, project_id, task_type, status, retry_count, request_params, progress_payload)
          VALUES (3001, 1, 'library_scan', 'queued', 0, '{}', :progress_payload)
          """
        ),
        {"progress_payload": '{"running":true,"message":"scanning"}'},
      )

    paused = self.client.post("/projects/1/tasks/3001/pause")
    self.assertEqual(paused.status_code, 200)
    paused_payload = paused.json()
    self.assertEqual(paused_payload["status"], "paused")
    self.assertEqual(paused_payload["progress_payload"]["message"], "paused")

    resumed = self.client.post("/projects/1/tasks/3001/resume")
    self.assertEqual(resumed.status_code, 200)
    resumed_payload = resumed.json()
    self.assertEqual(resumed_payload["status"], "queued")
    self.assertNotIn("pause_requested", resumed_payload["progress_payload"])

  def test_ai_jobs_failed_list_can_filter_job_type(self) -> None:
    with self._engine.begin() as conn:
      conn.execute(
        sa.text(
          """
          INSERT INTO ai_jobs (id, photo_id, project_id, job_type, status)
          VALUES (902, 101, 1, 'analyze', 'failed')
          """
        )
      )

    res = self.client.get("/projects/1/ai/jobs?status=failed&job_type=analyze,reanalyze")
    self.assertEqual(res.status_code, 200)
    payload = res.json()
    self.assertEqual(payload["total"], 1)
    self.assertEqual(payload["items"][0]["job_type"], "analyze")

  def test_retry_failed_can_filter_job_type(self) -> None:
    with self._engine.begin() as conn:
      conn.execute(
        sa.text(
          """
          INSERT INTO ai_jobs (id, photo_id, project_id, job_type, status)
          VALUES (902, 101, 1, 'analyze', 'failed')
          """
        )
      )

    retry = self.client.post("/projects/1/ai/jobs/retry-failed?job_type=analyze,reanalyze")
    self.assertEqual(retry.status_code, 200)
    self.assertEqual(retry.json()["retried_jobs"], 1)

    with self._engine.begin() as conn:
      rows = conn.execute(
        sa.text(
          """
          SELECT id, status FROM ai_jobs
          WHERE project_id = 1 AND id IN (901, 902)
          ORDER BY id ASC
          """
        )
      ).fetchall()
    self.assertEqual([(row[0], row[1]) for row in rows], [(901, "failed"), (902, "queued")])

  def test_retry_failed_face_scan_queues_project_task(self) -> None:
    retry = self.client.post("/projects/1/ai/jobs/retry-failed?job_type=face_scan")
    self.assertEqual(retry.status_code, 200)
    payload = retry.json()
    self.assertEqual(payload["retried_jobs"], 0)
    self.assertEqual(payload["task_created"], True)
    self.assertEqual(payload["task_status"], "queued")
    self.assertIsNotNone(payload["task_id"])

    with self._engine.begin() as conn:
      job_row = conn.execute(
        sa.text(
          """
          SELECT status FROM ai_jobs
          WHERE project_id = 1 AND id = 901
          """
        )
      ).first()
      task_row = conn.execute(
        sa.text(
          """
          SELECT task_type, status FROM project_tasks
          WHERE project_id = 1
          """
        )
      ).first()

    self.assertEqual(job_row[0], "failed")
    self.assertEqual((task_row[0], task_row[1]), ("face_scan_project", "queued"))

  def test_face_scan_project_task_replaces_old_failed_jobs_on_retry_scope(self) -> None:
    retry = self.client.post("/projects/1/ai/jobs/retry-failed?job_type=face_scan")
    self.assertEqual(retry.status_code, 200)

    db = self._SessionLocal()
    task = db.query(ProjectTask).filter(ProjectTask.project_id == 1).first()
    self.assertIsNotNone(task)
    ProjectTaskAppService(db, session_factory=self._SessionLocal).process_task(task)
    db.close()

    with self._engine.begin() as conn:
      rows = conn.execute(
        sa.text(
          """
          SELECT status FROM ai_jobs
          WHERE project_id = 1 AND photo_id = 103 AND job_type = 'face_scan'
          ORDER BY id ASC
          """
        )
      ).fetchall()

    self.assertEqual([row[0] for row in rows], ["queued"])
