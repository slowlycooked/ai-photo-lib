from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text

from app.services.startup_schema_service import StartupSchemaCheckError, validate_required_tables


class StartupSchemaServiceTest(unittest.TestCase):
    def _engine(self):
        return create_engine("sqlite+pysqlite:///:memory:")

    def _bootstrap(self, engine, revision: str | None):
        with engine.begin() as conn:
            if revision is not None:
                conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255) NOT NULL)"))
                conn.execute(
                    text("INSERT INTO alembic_version(version_num) VALUES (:rev)"),
                    {"rev": revision},
                )

    def test_passes_when_required_tables_exist(self):
        engine = self._engine()
        self._bootstrap(engine, revision="021_add_photo_derivatives")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photos (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE ai_jobs (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE project_face_settings (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE face_detections (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photo_derivatives (id INTEGER PRIMARY KEY)"))

        validate_required_tables(
            engine,
            required_tables=(
                "projects",
                "photos",
                "ai_jobs",
                "project_face_settings",
                "face_detections",
                "photo_derivatives",
            ),
        )

    def test_raises_with_migration_hint_when_tables_missing(self):
        engine = self._engine()
        self._bootstrap(engine, revision="021_add_photo_derivatives")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photos (id INTEGER PRIMARY KEY)"))

        with self.assertRaises(StartupSchemaCheckError) as ctx:
            validate_required_tables(engine, required_tables=("projects", "photos", "face_detections"))

        msg = str(ctx.exception)
        self.assertIn("face_detections", msg)
        self.assertIn("schema drift", msg)
        self.assertIn("alembic upgrade head", msg)

    def test_raises_when_alembic_version_table_missing(self):
        engine = self._engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))

        with self.assertRaises(StartupSchemaCheckError) as ctx:
            validate_required_tables(engine, required_tables=("projects", "photos"))

        msg = str(ctx.exception)
        self.assertIn("alembic_version", msg)
        self.assertIn("alembic upgrade head", msg)


if __name__ == "__main__":
    unittest.main()
