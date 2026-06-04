from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.routers.health import _alembic_check, _collect_schema_issues, _schema_preflight_check
from app.services.startup_schema_service import _alembic_head_revision


class HealthRouterTest(unittest.TestCase):
    def _session(self) -> Session:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        return Session(engine)

    def test_alembic_check_fails_when_revision_table_is_missing(self) -> None:
        db = self._session()
        try:
            issues = _collect_schema_issues(db)

            check = _alembic_check(db, issues)
        finally:
            db.close()

        self.assertEqual(check["status"], "fail")
        self.assertIn("alembic_version table is missing", check["message"])

    def test_alembic_check_fails_when_revision_is_not_head(self) -> None:
        db = self._session()
        try:
            db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL)"))
            db.execute(
                text("INSERT INTO alembic_version(version_num) VALUES ('026_add_semantic_concepts')")
            )
            db.commit()
            issues = _collect_schema_issues(db)

            check = _alembic_check(db, issues)
        finally:
            db.close()

        self.assertEqual(check["status"], "fail")
        self.assertIn("expected head", check["message"])

    def test_schema_preflight_ignores_alembic_and_pgvector_issues(self) -> None:
        check = _schema_preflight_check(
            [
                "alembic revision is 'old', expected head 'new'",
                "pgvector extension 'vector' is missing",
                "missing required tables [photo_embeddings]",
            ]
        )

        self.assertEqual(check["status"], "fail")
        self.assertIn("photo_embeddings", check["message"])
        self.assertNotIn("pgvector", check["message"])
        self.assertNotIn("alembic revision", check["message"])

    def test_alembic_check_passes_when_only_non_alembic_issues_exist(self) -> None:
        db = self._session()
        try:
            db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL)"))
            db.execute(
                text("INSERT INTO alembic_version(version_num) VALUES (:rev)"),
                {"rev": _alembic_head_revision()},
            )
            db.commit()

            check = _alembic_check(db, ["missing required tables [photo_embeddings]"])
        finally:
            db.close()

        self.assertEqual(check["status"], "ok")
        self.assertEqual(check["message"], _alembic_head_revision())


if __name__ == "__main__":
    unittest.main()
