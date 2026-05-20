from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Generator

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# Required before importing app.config.Settings at module import time.
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
  people_count INTEGER,
  confidence REAL,
  raw_result TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ai_jobs (
  id INTEGER PRIMARY KEY,
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

CREATE TABLE photo_embeddings (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    photo_id INTEGER NOT NULL,
    caption_embedding TEXT,
    tag_embedding TEXT,
    ocr_embedding TEXT,
    caption_text_hash TEXT,
    tag_text_hash TEXT,
    ocr_text_hash TEXT,
    embedding_model TEXT,
    embedding_dimension INTEGER,
    embedding_status TEXT NOT NULL DEFAULT 'ready',
    embedding_error TEXT,
    embedded_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, photo_id)
);

CREATE TABLE project_prompt_templates (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL DEFAULT 'image_analysis',
    system_prompt TEXT,
    user_prompt TEXT NOT NULL,
    output_schema TEXT,
    is_active BOOLEAN NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_project_prompt_templates_project_id_id UNIQUE (project_id, id)
);

CREATE TABLE project_ai_settings (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'llama-server',
    endpoint_url TEXT NOT NULL,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL DEFAULT 0,
    top_p REAL NOT NULL DEFAULT 0.8,
    max_tokens INTEGER NOT NULL DEFAULT 1024,
    retry_count INTEGER NOT NULL DEFAULT 1,
    output_language TEXT NOT NULL DEFAULT 'zh-CN',
    json_parse_strategy TEXT NOT NULL DEFAULT 'auto_extract',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_prompt_template_id INTEGER,
    CONSTRAINT fk_project_ai_settings_active_prompt_same_project
        FOREIGN KEY (project_id, active_prompt_template_id)
        REFERENCES project_prompt_templates (project_id, id)
);
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO photos (id, project_id, file_path, file_name, status)
VALUES (101, 1, '/tmp/a/a.jpg', 'a.jpg', 'indexed'),
       (202, 2, '/tmp/b/b.jpg', 'b.jpg', 'indexed');

INSERT INTO photo_ai_analysis (id, project_id, photo_id, caption)
VALUES (1, 2, 202, 'from project b');

INSERT INTO project_prompt_templates (id, project_id, name, user_prompt, is_active, version)
VALUES (1001, 1, 'Prompt A', 'A prompt', 1, 1),
       (2002, 2, 'Prompt B', 'B prompt', 1, 1);

INSERT INTO photo_embeddings (id, project_id, photo_id, embedding_model, embedding_dimension, embedding_status)
VALUES (1, 2, 202, 'test-model', 1024, 'ready');
"""


class ProjectIsolationEndpointsTest(unittest.TestCase):
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

    def test_project_cannot_read_other_project_photo(self) -> None:
        res = self.client.get("/projects/1/photos/202")
        self.assertEqual(res.status_code, 404)

    def test_project_can_read_own_photo(self) -> None:
        res = self.client.get("/projects/2/photos/202")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["id"], 202)
        self.assertEqual(body["project_id"], 2)

    def test_project_cannot_read_other_project_photo_ai(self) -> None:
        res = self.client.get("/projects/1/photos/202/ai")
        self.assertEqual(res.status_code, 404)

    def test_project_can_read_own_photo_ai(self) -> None:
        res = self.client.get("/projects/2/photos/202/ai")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["photo_id"], 202)

    def test_project_cannot_test_prompt_with_other_project_photo(self) -> None:
        res = self.client.post(
            "/projects/1/prompt-templates/test",
            json={"image_id": 202},
        )
        self.assertEqual(res.status_code, 404)

    def test_project_ai_start_only_queues_own_photos(self) -> None:
        res = self.client.post("/projects/1/ai/analyze/start")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["created_jobs"], 1)

    def test_active_prompt_fk_blocks_cross_project_template(self) -> None:
        with self._engine.begin() as conn:
            with self.assertRaises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO project_ai_settings
                            (id, project_id, endpoint_url, model_name, active_prompt_template_id)
                        VALUES
                            (1, 1, 'http://example.invalid/v1', 'demo-model', 2002)
                        """
                    )
                )

    def test_rebuild_embeddings_skips_existing_queued_job(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO ai_jobs (id, photo_id, project_id, job_type, status)
                    VALUES (9001, 202, 2, 'embed', 'queued')
                    """
                )
            )

        res = self.client.post("/projects/2/ai/embeddings/rebuild")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["created_jobs"], 0)
        self.assertEqual(body["skipped_existing_jobs"], 1)

    def test_rebuild_embeddings_force_true_creates_jobs_for_ready_embeddings(self) -> None:
        res = self.client.post("/projects/2/ai/embeddings/rebuild?force=true")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["created_jobs"], 1)
        self.assertEqual(body["total_checked"], 1)


if __name__ == "__main__":
    unittest.main()
