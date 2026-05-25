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
    content_embedding TEXT,
    caption_text_hash TEXT,
    tag_text_hash TEXT,
    ocr_text_hash TEXT,
    content_text_hash TEXT,
    embedding_model TEXT,
    embedding_dimension INTEGER,
    embedding_input_version TEXT,
    embedding_status TEXT NOT NULL DEFAULT 'ready',
    embedding_error TEXT,
    embedded_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, photo_id)
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

CREATE TABLE project_search_settings (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE,
    default_mode TEXT NOT NULL DEFAULT 'hybrid',
    keyword_top_k INTEGER NOT NULL DEFAULT 2000,
    vector_top_k INTEGER NOT NULL DEFAULT 200,
    page_size_default INTEGER NOT NULL DEFAULT 50,
    page_size_max INTEGER NOT NULL DEFAULT 200,
    rrf_k INTEGER NOT NULL DEFAULT 60,
    keyword_weight REAL NOT NULL DEFAULT 0.40,
    vector_weight REAL NOT NULL DEFAULT 0.60,
    vector_min_score REAL NOT NULL DEFAULT 0.30,
    keyword_field_weights TEXT,
    vector_field_weights TEXT,
    ocr_query_vector_field_weights TEXT,
    enable_query_understanding BOOLEAN NOT NULL DEFAULT 1,
    enable_structured_filters BOOLEAN NOT NULL DEFAULT 1,
    enable_semantic_tag_boost BOOLEAN NOT NULL DEFAULT 0,
    search_quality_settings TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO photos (
    id, project_id, file_path, file_name, status, taken_at,
    city, district, formatted_address, created_at, updated_at
)
VALUES
    (101, 1, '/tmp/a/a.jpg',   'a.jpg',   'indexed', '2024-05-03 08:00:00', '杭州', '西湖区', '中国浙江省杭州市西湖区龙井路', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (102, 1, '/tmp/a/cat.jpg', 'cat.jpg', 'indexed', '2024-05-14 10:00:00', '上海', '浦东新区', '中国上海市浦东新区世纪大道', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (103, 1, '/tmp/a/dog.jpg', 'dog.jpg', 'indexed', '2023-05-02 09:00:00', '杭州', '余杭区', '中国浙江省杭州市余杭区', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    (202, 2, '/tmp/b/b.jpg',   'b.jpg',   'indexed', '2024-05-05 12:00:00', '杭州', '西湖区', '中国浙江省杭州市西湖区', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO photo_ai_analysis (id, project_id, photo_id, caption, object_tags)
VALUES (2, 1, 102, 'a cat photo', '["猫"]'),
       (3, 1, 103, 'a dog photo', '["狗"]'),
       (4, 2, 202, 'from project b', '["猫"]');

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

    # ── Tag filter tests ──────────────────────────────────────────────────────

    def test_tag_filter_count_equals_tag_search_total(self) -> None:
        """Tags page shows 猫=1 for project 1; tag filter must return total=1."""
        res = self.client.get(
            "/projects/1/search?filter=tag&tag_field=object_tags&tag_value=%E7%8C%AB"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["photo_id"], 102)

    def test_tag_filter_field_isolation(self) -> None:
        """object_tags:猫=1 in project 1; search_keywords must not add extra results."""
        # Only photo 102 has object_tags=["猫"] in project 1.
        res = self.client.get(
            "/projects/1/search?filter=tag&tag_field=object_tags&tag_value=%E7%8C%AB"
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        # Must not return photo 103 (狗) or cross-project photo 202.
        photo_ids = [item["photo_id"] for item in body["items"]]
        self.assertNotIn(103, photo_ids)
        self.assertNotIn(202, photo_ids)

    def test_tag_filter_project_isolation(self) -> None:
        """Both projects have 猫 in object_tags; each project sees only its own photos."""
        res_p1 = self.client.get(
            "/projects/1/search?filter=tag&tag_field=object_tags&tag_value=%E7%8C%AB"
        )
        res_p2 = self.client.get(
            "/projects/2/search?filter=tag&tag_field=object_tags&tag_value=%E7%8C%AB"
        )
        self.assertEqual(res_p1.status_code, 200)
        self.assertEqual(res_p2.status_code, 200)
        ids_p1 = {item["photo_id"] for item in res_p1.json()["items"]}
        ids_p2 = {item["photo_id"] for item in res_p2.json()["items"]}
        self.assertIn(102, ids_p1)
        self.assertNotIn(202, ids_p1)
        self.assertIn(202, ids_p2)
        self.assertNotIn(102, ids_p2)

    def test_tag_filter_invalid_field_rejected(self) -> None:
        """tag_field not in allowlist must return 422."""
        res = self.client.get(
            "/projects/1/search?filter=tag&tag_field=caption&tag_value=test"
        )
        self.assertEqual(res.status_code, 422)

    def test_tag_filter_missing_tag_value_rejected(self) -> None:
        """filter=tag without tag_value must return 422."""
        res = self.client.get(
            "/projects/1/search?filter=tag&tag_field=object_tags"
        )
        self.assertEqual(res.status_code, 422)

    def test_search_time_and_place_filters_are_project_scoped(self) -> None:
        res = self.client.get("/projects/1/search?q=2024年5月 杭州")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["photo_id"], 101)
        self.assertEqual(body["items"][0]["city"], "杭州")


if __name__ == "__main__":
    unittest.main()
