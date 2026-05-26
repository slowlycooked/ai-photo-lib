from __future__ import annotations

import os
import tempfile

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")
os.environ["FACE_RECOGNITION_ENABLED"] = "false"

from app.services.project_face_settings_service import (  # noqa: E402
    get_or_create_project_face_settings,
    reset_project_face_settings,
    update_project_face_settings,
)
from app.services import project_face_settings_service  # noqa: E402
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
            VALUES (1, 'People Project', '/tmp/lib', '/tmp/thumbs', 1)
            """
        )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def _force_face_recognition_default_disabled() -> None:
    project_face_settings_service.global_settings.face_recognition_enabled = False


def test_get_or_create_project_face_settings_uses_defaults() -> None:
    _force_face_recognition_default_disabled()
    db = _make_session()
    try:
        row = get_or_create_project_face_settings(db, 1)
        assert row.project_id == 1
        assert row.face_provider == "opencv"
        assert row.face_detector_model == "yunet"
        assert row.face_embedding_model == "sface"
        assert row.face_recognition_enabled is False
        assert row.auto_accept_threshold == 0.62
    finally:
        db.close()


def test_update_and_reset_project_face_settings() -> None:
    _force_face_recognition_default_disabled()
    db = _make_session()
    try:
        update_project_face_settings(
            db,
            1,
            {
                "face_recognition_enabled": True,
                "auto_accept_threshold": 0.71,
                "review_threshold": 0.55,
                "store_face_crops": False,
            },
        )
        updated = get_or_create_project_face_settings(db, 1)
        assert updated.face_recognition_enabled is True
        assert updated.auto_accept_threshold == 0.71
        assert updated.review_threshold == 0.55
        assert updated.store_face_crops is False

        reset = reset_project_face_settings(db, 1)
        assert reset.face_recognition_enabled is False
        assert reset.auto_accept_threshold == 0.62
        assert reset.review_threshold == 0.48
        assert reset.store_face_crops is True
    finally:
        db.close()
