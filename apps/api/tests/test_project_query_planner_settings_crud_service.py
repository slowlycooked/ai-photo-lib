from __future__ import annotations

import os
import tempfile
import unittest.mock

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")
os.environ.setdefault("QUERY_PLANNER_BASE_URL", "http://127.0.0.1:18084/v1")
os.environ["QUERY_PLANNER_ALIAS"] = "qwen3-4b-query-planner"

from app.services.project_query_planner_settings_service import (  # noqa: E402
    get_or_create_project_query_planner_settings,
    reset_project_query_planner_settings,
    update_project_query_planner_settings,
)
from app.models import project  # noqa: F401, E402


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

CREATE TABLE project_query_planner_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
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
  planner_version TEXT NOT NULL DEFAULT 'llm_query_planner_v1',
  prompt_template TEXT,
  system_prompt TEXT,
  fallback_mode TEXT NOT NULL DEFAULT 'rule_fallback',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_session() -> Session:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = sa.create_engine(f"sqlite:///{tmp.name}", future=True)
    with engine.begin() as conn:
        for statement in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            """
            INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
            VALUES (1, 'Planner Project', '/tmp/lib', '/tmp/thumbs', 1)
            """
        )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def test_get_or_create_project_query_planner_settings_defaults() -> None:
    import app.services.project_query_planner_settings_service as _svc
    db = _make_session()
    try:
        with unittest.mock.patch.object(_svc, "global_settings") as mock_settings:
            mock_settings.query_planner_base_url = "http://127.0.0.1:18084/v1"
            mock_settings.query_planner_alias = "qwen3-4b-query-planner"
            mock_settings.openai_api_key = "test"
            row = get_or_create_project_query_planner_settings(db, 1)
        assert row.project_id == 1
        assert row.enabled is True
        assert row.provider == "llama-server"
        assert row.endpoint_url == "http://127.0.0.1:18084/v1"
        assert row.model_name == "qwen3-4b-query-planner"
        assert row.max_tokens == 220
    finally:
        db.close()


def test_update_and_reset_project_query_planner_settings() -> None:
    import app.services.project_query_planner_settings_service as _svc
    db = _make_session()
    try:
        updated = update_project_query_planner_settings(
            db,
            1,
            {
                "enabled": True,
                "endpoint_url": "http://127.0.0.1:18084/v1/chat/completions",
                "model_name": "qwen3-4b-query-planner",
                "temperature": 0.0,
                "top_p": 0.8,
                "max_tokens": 768,
            },
        )
        assert updated.enabled is True
        assert updated.model_name == "qwen3-4b-query-planner"
        assert updated.max_tokens == 768

        with unittest.mock.patch.object(_svc, "global_settings") as mock_settings:
            mock_settings.query_planner_base_url = "http://127.0.0.1:18084/v1"
            mock_settings.query_planner_alias = "qwen3-4b-query-planner"
            mock_settings.openai_api_key = "test"
            reset = reset_project_query_planner_settings(db, 1)
        assert reset.enabled is True
        assert reset.model_name == "qwen3-4b-query-planner"
        assert reset.endpoint_url == "http://127.0.0.1:18084/v1"
        assert reset.max_tokens == 220
    finally:
        db.close()
