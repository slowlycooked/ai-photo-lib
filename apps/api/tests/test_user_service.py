from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.user import ProjectMembership, User  # noqa: E402
from app.schemas.user import UserCreate, UserProjectAccessUpsert  # noqa: E402
from app.services.user_service import DuplicateUserError, UserService  # noqa: E402


def _make_session():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = sa.create_engine(f"sqlite:///{tmp.name}", future=True)
    with engine.begin() as conn:
                conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                conn.exec_driver_sql(
                        """
                        CREATE TABLE projects (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL,
                            description TEXT,
                            photo_library_path TEXT NOT NULL,
                            thumbnail_path TEXT,
                            is_default BOOLEAN NOT NULL DEFAULT 0,
                            deleted_at TEXT,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                )
                conn.exec_driver_sql(
                        """
                        CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL UNIQUE,
                            password_hash TEXT NOT NULL,
                            display_name TEXT,
                            role TEXT NOT NULL DEFAULT 'viewer',
                            status TEXT NOT NULL DEFAULT 'active',
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                )
                conn.exec_driver_sql(
                        """
                        CREATE TABLE project_memberships (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            project_id INTEGER NOT NULL,
                            user_id INTEGER NOT NULL,
                            project_role TEXT NOT NULL DEFAULT 'viewer',
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                        )
                        """
                )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return SessionLocal(), tmp.name


class UserServiceTest(unittest.TestCase):
    def test_create_user_rolls_back_on_commit_integrity_error(self) -> None:
        db, db_path = _make_session()
        try:
            service = UserService(db)
            body = UserCreate(
                username="alice",
                password="secret123",
                display_name="Alice",
                role="viewer",
                status="active",
            )

            with patch.object(db, "commit", side_effect=IntegrityError("stmt", "params", Exception("boom"))):
                with self.assertRaises(DuplicateUserError):
                    service.create_user(body)

            self.assertEqual(db.query(User).count(), 0)
        finally:
            db.close()
            os.unlink(db_path)

    def test_delete_user_cascades_memberships(self) -> None:
        db, db_path = _make_session()
        try:
            db.execute(sa.text("INSERT INTO projects (id, name, photo_library_path, is_default, deleted_at) VALUES (1, 'P', '/tmp', 0, NULL)"))
            db.execute(
                sa.text(
                    "INSERT INTO users (id, username, password_hash, display_name, role, status) "
                    "VALUES (1, 'alice', 'hash', 'Alice', 'viewer', 'active')"
                )
            )
            db.execute(
                sa.text(
                    "INSERT INTO project_memberships (project_id, user_id, project_role) VALUES (1, 1, 'viewer')"
                )
            )
            db.commit()

            service = UserService(db)
            service.delete_user(1)

            self.assertEqual(db.query(User).count(), 0)
            self.assertEqual(db.query(ProjectMembership).count(), 0)
        finally:
            db.close()
            os.unlink(db_path)

    def test_user_project_access_roundtrip(self) -> None:
        db, db_path = _make_session()
        try:
            db.execute(sa.text("INSERT INTO projects (id, name, photo_library_path, is_default, deleted_at) VALUES (1, 'Alpha', '/tmp/alpha', 1, NULL)"))
            db.execute(sa.text("INSERT INTO projects (id, name, photo_library_path, is_default, deleted_at) VALUES (2, 'Beta', '/tmp/beta', 0, NULL)"))
            db.execute(
                sa.text(
                    "INSERT INTO users (id, username, password_hash, display_name, role, status) "
                    "VALUES (1, 'alice', 'hash', 'Alice', 'viewer', 'active')"
                )
            )
            db.commit()

            service = UserService(db)
            self.assertEqual(service.list_user_project_access(1), [])

            rows = service.upsert_user_project_access(1, 1, UserProjectAccessUpsert(project_role="viewer"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].project_id, 1)
            self.assertEqual(rows[0].project_role, 'viewer')

            rows = service.upsert_user_project_access(1, 2, UserProjectAccessUpsert(project_role="manager"))
            self.assertEqual([row.project_id for row in rows], [1, 2])
            self.assertEqual(rows[1].project_role, 'manager')

            rows = service.delete_user_project_access(1, 1)
            self.assertEqual([row.project_id for row in rows], [2])
        finally:
            db.close()
            os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()