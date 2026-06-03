from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.project_app_service import repair_legacy_project_library_paths  # noqa: E402


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
"""


class RepairLegacyProjectLibraryPathsTest(unittest.TestCase):
    def test_rewrites_legacy_container_paths_to_configured_host_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "projects.db"
            engine = sa.create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False},
                future=True,
            )
            SessionLocal = sessionmaker(bind=engine, future=True)

            with engine.begin() as conn:
                conn.execute(sa.text(SCHEMA_SQL))
                conn.execute(
                    sa.text(
                        "INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default) "
                        "VALUES (1, 'Default', '/photos', '/tmp/thumbs', 1), "
                        "(2, 'Nested', '/photos/travel', '/tmp/thumbs', 0), "
                        "(3, 'Modern', '/Users/unclema/Desktop/ai-lib/keep', '/tmp/thumbs', 0)"
                    )
                )

            db = SessionLocal()
            try:
                repaired = repair_legacy_project_library_paths(db)
                self.assertEqual(repaired, 2)

                rows = db.execute(
                    sa.text("SELECT id, photo_library_path FROM projects ORDER BY id")
                ).all()
                self.assertEqual(
                    rows,
                    [
                        (1, "/tmp"),
                        (2, "/tmp/travel"),
                        (3, "/Users/unclema/Desktop/ai-lib/keep"),
                    ],
                )
            finally:
                db.close()
