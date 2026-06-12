from __future__ import annotations

import os
import tempfile
import unittest
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
os.environ.setdefault("QUERY_PLANNER_BASE_URL", "http://127.0.0.1:18084/v1")
os.environ.setdefault("QUERY_PLANNER_ALIAS", "qwen3-4b-query-planner")

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
  keyword_field_weights JSON,
  vector_field_weights JSON,
  ocr_query_vector_field_weights JSON,
  enable_query_understanding BOOLEAN NOT NULL DEFAULT 1,
  enable_structured_filters BOOLEAN NOT NULL DEFAULT 0,
  enable_semantic_tag_boost BOOLEAN NOT NULL DEFAULT 0,
  search_result_cache_ttl_seconds INTEGER NOT NULL DEFAULT 600,
  search_quality_settings JSON,
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

CREATE TABLE project_query_planner_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  enabled BOOLEAN NOT NULL DEFAULT 1,
  provider TEXT NOT NULL DEFAULT 'llama-server',
  endpoint_url TEXT,
  api_key TEXT,
  model_name TEXT,
  temperature REAL NOT NULL DEFAULT 0,
  top_p REAL NOT NULL DEFAULT 0.1,
  max_tokens INTEGER NOT NULL DEFAULT 220,
  timeout_seconds INTEGER NOT NULL DEFAULT 20,
  json_parse_strategy TEXT NOT NULL DEFAULT 'strict_json_then_extract',
  planner_version TEXT NOT NULL DEFAULT 'llm_query_planner_v1',
  prompt_template TEXT,
  system_prompt TEXT,
  fallback_mode TEXT NOT NULL DEFAULT 'rule_fallback',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES
  (1, 'Search Project', '/tmp/p1', '/tmp/t1', 1),
  (2, 'Embedding Fallback Project', '/tmp/p2', '/tmp/t2', 0);

INSERT INTO project_search_settings (
  id, project_id, default_mode, keyword_top_k, vector_top_k, page_size_default, page_size_max,
  rrf_k, keyword_weight, vector_weight, vector_min_score,
  keyword_field_weights, vector_field_weights, ocr_query_vector_field_weights,
  enable_query_understanding, enable_structured_filters, enable_semantic_tag_boost,
  search_result_cache_ttl_seconds,
  search_quality_settings
)
VALUES (
  1, 1, 'hybrid', 1500, 321, 50, 200,
  44, 0.4, 0.6, 0.31,
  '{"caption": 2.0}', '{"content_embedding": 1.0}', '{"ocr_embedding": 1.0}',
  1, 0, 1, 600,
  '{"vector_strict_score": 0.5, "query_planner_enabled": false, "query_planner_max_tokens": 333}'
);

INSERT INTO project_embedding_settings (
  id, project_id, endpoint_url, model_name,
  search_content_vector_weight, search_tag_vector_weight,
  search_caption_vector_weight, search_ocr_vector_weight
)
VALUES (
  1, 2, 'http://127.0.0.1:9999/v1', 'embedding-test',
  0.1, 0.2, 0.3, 0.4
);
"""


class ProjectEffectiveSettingsEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        self._engine = sa.create_engine(
            f"sqlite:///{self._db_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
        )

        with self._engine.begin() as conn:
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

    def test_effective_settings_endpoint_explains_project_sources(self) -> None:
        response = self.client.get("/projects/1/settings/effective")

        assert response.status_code == 200
        search = response.json()["search"]
        assert search["vector_top_k"] == {
            "value": 321,
            "source": "project_search_settings",
        }
        assert search["vector_strict_score"] == {
            "value": 0.5,
            "source": "project_search_settings.search_quality_settings",
        }
        assert search["query_planner_enabled"] == {
            "value": False,
            "source": "project_search_settings.search_quality_settings",
        }
        assert search["query_planner_max_tokens"] == {
            "value": 333,
            "source": "project_search_settings.search_quality_settings",
        }
        assert search["query_planner_model_name"]["source"] == "global_config"

    def test_effective_settings_endpoint_explains_embedding_fallback(self) -> None:
        response = self.client.get("/projects/2/settings/effective")

        assert response.status_code == 200
        search = response.json()["search"]
        assert search["vector_top_k"]["source"] == "global_config"
        assert search["vector_field_weights"] == {
            "value": {
                "content_embedding": 0.1,
                "tag_embedding": 0.2,
                "caption_embedding": 0.3,
                "ocr_embedding": 0.4,
            },
            "source": "project_embedding_settings",
        }
