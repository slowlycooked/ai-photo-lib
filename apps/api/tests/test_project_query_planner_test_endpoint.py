from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Generator
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
os.environ.setdefault("AUTH_ENABLED", "0")

from app.api.deps import require_project_manager  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.project import Project  # noqa: E402


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
  keyword_weight REAL NOT NULL DEFAULT 0.40,
  vector_weight REAL NOT NULL DEFAULT 0.60,
  vector_min_score REAL NOT NULL DEFAULT 0.30,
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

CREATE TABLE project_query_planner_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  ai_service_profile_id INTEGER,
  enabled BOOLEAN NOT NULL DEFAULT 0,
  provider TEXT NOT NULL DEFAULT 'llama-server',
  endpoint_url TEXT,
  api_key TEXT,
  model_name TEXT,
  temperature REAL NOT NULL DEFAULT 0,
  top_p REAL NOT NULL DEFAULT 0.1,
  max_tokens INTEGER NOT NULL DEFAULT 220,
  timeout_seconds INTEGER NOT NULL DEFAULT 3,
  json_parse_strategy TEXT NOT NULL DEFAULT 'strict_json_then_extract',
  planner_version TEXT NOT NULL DEFAULT 'llm_query_planner_v2',
  prompt_template TEXT,
  system_prompt TEXT,
  fallback_mode TEXT NOT NULL DEFAULT 'rule_fallback',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Planner Project', '/tmp/p', '/tmp/p-thumb', 1);

INSERT INTO project_search_settings (
  id, project_id, default_mode, keyword_top_k, vector_top_k, page_size_default, page_size_max,
  rrf_k, keyword_weight, vector_weight, vector_min_score,
  enable_query_understanding, enable_structured_filters, enable_semantic_tag_boost,
  search_result_cache_ttl_seconds
)
VALUES (
  1, 1, 'hybrid', 2000, 200, 50, 200,
  60, 0.4, 0.6, 0.3,
  1, 0, 0, 600
);

INSERT INTO project_query_planner_settings (
  id, project_id, enabled, provider, endpoint_url, api_key, model_name,
  temperature, top_p, max_tokens, timeout_seconds,
  json_parse_strategy, planner_version, prompt_template, system_prompt, fallback_mode
)
VALUES (
  1, 1, 1, 'llama-server', 'http://127.0.0.1:18084/v1/chat/completions', 'test', 'Qwen3-8B-Query-Planner',
  0, 0.1, 220, 3,
  'strict_json_then_extract', 'llm_query_planner_v2', '', '', 'rule_fallback'
);
"""


class ProjectQueryPlannerTestEndpointE2ETest(unittest.TestCase):
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

        def override_require_project_manager(project_id: int) -> Project:
            db = self._SessionLocal()
            try:
                project = (
                    db.query(Project)
                    .filter(Project.id == project_id, Project.deleted_at.is_(None))
                    .first()
                )
                if project is None:
                    raise RuntimeError("Project not found")
                return project
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_project_manager] = (
            override_require_project_manager
        )
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self._engine.dispose()
        if os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_query_planner_test_endpoint_success(self) -> None:
        llm_json = """
        {
          "version": "2",
          "intent": "photo_search",
          "filters": {
            "time_ranges": [],
            "locations": [],
            "people": [],
            "camera": [],
            "has_gps": null,
            "media_types": ["photo"],
            "albums": []
          },
          "lexical": {
            "required": ["动物"],
            "preferred": ["宠物", "猫", "狗"],
            "excluded": ["玩具动物"]
          },
          "semantic": {
            "concepts": ["动物"],
            "queries": ["查找包含动物主体的照片"]
          },
          "visual": {
            "objects": ["动物"],
            "scenes": [],
            "activities": [],
            "attributes": []
          },
          "ranking": {
            "sort": [{"field": "relevance", "order": "desc"}]
          },
          "unresolved": {
            "people": [],
            "locations": []
          },
          "confidence": 0.91
        }
        """
        with patch(
            "app.services.search.query_planner.llm_query_planner.call_chat_completion",
            return_value=llm_json,
        ):
            res = self.client.post(
                "/projects/1/query-planner-settings/test",
                json={"query": "动物"},
            )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["query"], "动物")
        self.assertFalse(body["planner_debug"].get("used_fallback"))
        self.assertEqual(body["planner_debug"].get("planner_contract_version"), "2")
        self.assertEqual(body["parsed_query_plan"]["intent"], "semantic_photo_search")
        self.assertIn("动物", body["parsed_query_plan"]["exact_terms"])

    def test_query_planner_test_endpoint_fallback_on_planner_error(self) -> None:
        with patch(
            "app.services.search.query_planner.llm_query_planner.call_chat_completion",
            side_effect=ValueError("invalid planner output"),
        ):
            res = self.client.post(
                "/projects/1/query-planner-settings/test",
                json={"query": "夜景"},
            )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["planner_debug"].get("used_fallback"))
        self.assertTrue(str(body["planner_debug"].get("fallback_reason", "")).startswith("planner_error:"))
        self.assertIn("intent", body["parsed_query_plan"])

    def test_query_planner_test_endpoint_accepts_v2_optional_scalars(self) -> None:
        llm_json = """
        {
          "version": "2",
          "intent": "photo_search",
          "filters": {
            "time_ranges": [],
            "locations": [],
            "people": [],
            "camera": [],
            "has_gps": null,
            "media_types": [],
            "albums": []
          },
          "lexical": {
            "required": ["动物"],
            "preferred": ["宠物", "野生动物"],
            "excluded": []
          },
          "semantic": {
            "concepts": ["动物"],
            "queries": ["关于动物的图像内容"]
          },
          "visual": {
            "objects": ["动物"],
            "scenes": [],
            "activities": [],
            "attributes": []
          },
          "ranking": {
            "sort": []
          },
          "unresolved": {
            "people": [],
            "locations": []
          },
          "confidence": 0.95
        }
        """
        with patch(
            "app.services.search.query_planner.llm_query_planner.call_chat_completion",
            return_value=llm_json,
        ):
            res = self.client.post(
                "/projects/1/query-planner-settings/test",
                json={"query": "动物"},
            )

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["planner_debug"].get("used_fallback"))
        self.assertEqual(body["planner_debug"].get("planner_contract_version"), "2")
        self.assertIsNone(body["parsed_query_plan"]["metadata_filters"].get("has_gps"))

    def test_query_planner_test_endpoint_fallback_on_missing_config(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    UPDATE project_query_planner_settings
                    SET enabled = 1,
                        endpoint_url = NULL,
                        model_name = NULL
                    WHERE project_id = 1
                    """
                )
            )

        res = self.client.post(
            "/projects/1/query-planner-settings/test",
            json={"query": "张三在海边的合照"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["planner_debug"].get("used_fallback"))
        self.assertEqual(
            body["planner_debug"].get("fallback_reason"),
            "query_planner_missing_endpoint_or_model",
        )


if __name__ == "__main__":
    unittest.main()
