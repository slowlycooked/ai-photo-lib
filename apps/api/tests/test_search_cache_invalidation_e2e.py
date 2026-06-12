"""End-to-end test for search result cache invalidation on data mutations."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone
from typing import Generator

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
os.environ.setdefault("AUTH_ENABLED", "0")

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.ai import AIJob  # noqa: E402
from app.models.photo import Photo  # noqa: E402
from app.services.search.result_cache import get_project_search_cache_epoch  # noqa: E402
from app.models.project_task import ProjectTask  # noqa: E402


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
  deleted_at TEXT,
  UNIQUE(project_id, file_path)
);

CREATE TABLE photo_ai_analysis (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  model_name TEXT,
  model_version TEXT,
  caption TEXT,
  ocr_text TEXT,
  scene_tags TEXT,
  object_tags TEXT,
  activity_tags TEXT,
  quality_tags TEXT,
  location_clues TEXT,
  search_keywords TEXT,
  semantic_concepts TEXT,
  people_count INTEGER,
  confidence REAL,
  raw_result TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, photo_id)
);

CREATE TABLE ai_jobs (
  id INTEGER PRIMARY KEY,
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

CREATE TABLE project_search_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  default_mode TEXT NOT NULL DEFAULT 'hybrid',
  keyword_top_k INTEGER NOT NULL DEFAULT 2000,
  vector_top_k INTEGER NOT NULL DEFAULT 200,
  page_size_default INTEGER NOT NULL DEFAULT 50,
  page_size_max INTEGER NOT NULL DEFAULT 200,
  rrf_k INTEGER NOT NULL DEFAULT 60,
  keyword_weight REAL NOT NULL DEFAULT 0.55,
  vector_weight REAL NOT NULL DEFAULT 0.45,
  vector_min_score REAL NOT NULL DEFAULT 0.25,
  keyword_field_weights TEXT,
  vector_field_weights TEXT,
  ocr_query_vector_field_weights TEXT,
  enable_query_understanding BOOLEAN NOT NULL DEFAULT 1,
  enable_structured_filters BOOLEAN NOT NULL DEFAULT 0,
  enable_semantic_tag_boost BOOLEAN NOT NULL DEFAULT 0,
  search_result_cache_ttl_seconds INTEGER NOT NULL DEFAULT 600,
  search_quality_settings TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_embedding_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  provider TEXT NOT NULL DEFAULT 'openai-compatible',
  endpoint_url TEXT NOT NULL,
  api_key TEXT,
  model_name TEXT NOT NULL,
  embedding_dimension INTEGER NOT NULL DEFAULT 1024,
  batch_size INTEGER NOT NULL DEFAULT 16,
  timeout_seconds INTEGER NOT NULL DEFAULT 60,
  input_prefix_query TEXT,
  input_prefix_document TEXT,
  enabled BOOLEAN NOT NULL DEFAULT 1,
  search_content_vector_weight REAL NOT NULL DEFAULT 0.5,
  search_tag_vector_weight REAL NOT NULL DEFAULT 0.25,
  search_caption_vector_weight REAL NOT NULL DEFAULT 0.2,
  search_ocr_vector_weight REAL NOT NULL DEFAULT 0.05,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_tasks (
  id INTEGER PRIMARY KEY,
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

CREATE TABLE app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Cache Test Project', '/tmp/cache-test', '/tmp/cache-test-thumb', 1);

INSERT INTO photos (id, project_id, file_path, file_name, status, created_at, updated_at)
VALUES (1, 1, '/tmp/cache-test/photo1.jpg', 'photo1.jpg', 'ai_indexed', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO photo_ai_analysis (id, project_id, photo_id, caption, object_tags, created_at, updated_at)
VALUES (1, 1, 1, 'Test photo', '["cat"]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO project_search_settings (id, project_id, search_result_cache_ttl_seconds)
VALUES (1, 1, 600);

INSERT INTO project_embedding_settings (id, project_id, endpoint_url, model_name)
VALUES (1, 1, 'http://127.0.0.1:9999/v1', 'test-embed');
"""


class SearchCacheInvalidationE2ETest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._db_path = self._tmp.name
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
            conn.execute(sa.text("PRAGMA foreign_keys=ON"))
            for stmt in SCHEMA_SQL.split(";"):
                sql = stmt.strip()
                if sql:
                    conn.execute(sa.text(sql))
            for stmt in SEED_SQL.split(";"):
                sql = stmt.strip()
                if sql:
                    conn.execute(sa.text(sql))

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
        if os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_cache_invalidation_on_ai_job_success(self) -> None:
        """Test that search cache is invalidated after AI analysis completes."""
        with self._SessionLocal() as db:
            initial_epoch = get_project_search_cache_epoch(db, 1)
            self.assertEqual(initial_epoch, 0)

            job = (
                db.query(AIJob)
                .filter(AIJob.id == 1)
                .first()
            )
            if job is None:
                job = AIJob(
                    photo_id=1,
                    project_id=1,
                    job_type="embed",
                    status="queued",
                )
                db.add(job)
                db.commit()
                db.refresh(job)

        job_id = job.id
        with self._SessionLocal() as db:
            job = db.query(AIJob).filter(AIJob.id == job_id).first()
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            db.flush()

            photo = db.query(Photo).filter(Photo.id == 1).first()
            self.assertIsNotNone(photo)

            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.updated_at = job.finished_at
            job.error_message = None
            job.locked_by = None
            job.locked_at = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            db.flush()

            from app.services.search.result_cache import bump_project_search_cache_epoch
            bump_project_search_cache_epoch(db, 1, reason="test_embed_completed")
            db.commit()

            updated_epoch = get_project_search_cache_epoch(db, 1)

        self.assertGreater(updated_epoch, initial_epoch)

    def test_cache_invalidation_on_library_scan_task_success(self) -> None:
        """Test that search cache is invalidated after scan task completes."""
        with self._SessionLocal() as db:
            initial_epoch = get_project_search_cache_epoch(db, 1)
            self.assertEqual(initial_epoch, 0)

            task = ProjectTask(
                project_id=1,
                task_type="LIBRARY_SCAN",
                status="queued",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id

        with self._SessionLocal() as db:
            task = db.query(ProjectTask).filter(ProjectTask.id == task_id).first()
            self.assertIsNotNone(task)
            task.status = "running"
            db.flush()

            task.status = "success"
            task.progress_items_completed = 1
            task.progress_items_total = 1
            db.flush()

            from app.services.search.result_cache import bump_project_search_cache_epoch
            bump_project_search_cache_epoch(db, 1, reason="scan_completed")
            db.commit()

            updated_epoch = get_project_search_cache_epoch(db, 1)

        self.assertGreater(updated_epoch, initial_epoch)


if __name__ == "__main__":
    unittest.main()
