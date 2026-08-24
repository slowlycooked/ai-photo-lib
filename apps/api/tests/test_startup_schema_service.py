from __future__ import annotations

import unittest

from sqlalchemy import create_engine, text

from app.services.startup_schema_service import (
    StartupSchemaCheckError,
    _alembic_head_revision,
    collect_startup_schema_issues,
    validate_required_columns,
    validate_required_tables,
    validate_startup_schema,
)


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

    def test_collects_missing_user_management_tables(self):
        engine = self._engine()
        self._bootstrap(engine, revision=_alembic_head_revision())
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photos (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE ai_jobs (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photo_ai_analysis (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photo_embeddings (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE project_face_settings (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE face_detections (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE face_embeddings (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE persons (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE person_face_assignments (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE person_prototypes (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE face_negative_constraints (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE person_cannot_links (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE photo_derivatives (id INTEGER PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE project_tasks (id INTEGER PRIMARY KEY)"))

        issues = collect_startup_schema_issues(engine)

        self.assertTrue(any("users" in issue for issue in issues), issues)

    def test_raises_when_alembic_version_table_missing(self):
        engine = self._engine()
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY)"))

        with self.assertRaises(StartupSchemaCheckError) as ctx:
            validate_required_tables(engine, required_tables=("projects", "photos"))

        msg = str(ctx.exception)
        self.assertIn("alembic_version", msg)
        self.assertIn("alembic upgrade head", msg)

    def test_required_columns_pass_when_present(self):
        engine = self._engine()
        self._bootstrap(engine, revision="026_add_semantic_concepts")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE photo_ai_analysis ("
                    "id INTEGER PRIMARY KEY, "
                    "semantic_concepts TEXT"
                    ")"
                )
            )

        validate_required_columns(
            engine,
            required_columns={"photo_ai_analysis": ("semantic_concepts",)},
        )

    def test_required_columns_raise_with_drift_hint(self):
        engine = self._engine()
        self._bootstrap(engine, revision="026_add_semantic_concepts")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE photo_ai_analysis (id INTEGER PRIMARY KEY)"))

        with self.assertRaises(StartupSchemaCheckError) as ctx:
            validate_required_columns(
                engine,
                required_columns={"photo_ai_analysis": ("semantic_concepts",)},
            )

        msg = str(ctx.exception)
        self.assertIn("photo_ai_analysis.semantic_concepts", msg)
        self.assertIn("schema drift", msg)

    def test_collects_photo_embedding_column_drift(self):
        engine = self._engine()
        self._bootstrap(engine, revision=_alembic_head_revision())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE photo_embeddings ("
                    "id INTEGER PRIMARY KEY, "
                    "project_id INTEGER, "
                    "photo_id INTEGER, "
                    "embedding_status TEXT"
                    ")"
                )
            )

        issues = collect_startup_schema_issues(engine)

        self.assertTrue(
            any("photo_embeddings.caption_embedding" in issue for issue in issues),
            issues,
        )

    def test_collects_missing_project_task_partial_unique_indexes(self):
        engine = self._engine()
        self._bootstrap(engine, revision=_alembic_head_revision())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE project_tasks ("
                    "id INTEGER PRIMARY KEY, "
                    "project_id INTEGER, "
                    "task_type TEXT, "
                    "status TEXT"
                    ")"
                )
            )

        issues = collect_startup_schema_issues(engine)

        self.assertTrue(
            any("uq_project_tasks_one_active_scan" in issue for issue in issues),
            issues,
        )

    def test_collects_invalid_project_task_index_shape(self):
        engine = self._engine()
        self._bootstrap(engine, revision=_alembic_head_revision())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE project_tasks ("
                    "id INTEGER PRIMARY KEY, "
                    "project_id INTEGER, "
                    "task_type TEXT, "
                    "status TEXT"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX uq_project_tasks_one_active_scan "
                    "ON project_tasks (project_id)"
                )
            )

        issues = collect_startup_schema_issues(engine)

        self.assertTrue(
            any("not partial unique indexes" in issue for issue in issues),
            issues,
        )

    def test_accepts_required_non_unique_lookup_index(self):
        engine = self._engine()
        self._bootstrap(engine, revision=_alembic_head_revision())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE photo_quarantine_items ("
                    "id INTEGER PRIMARY KEY, "
                    "project_id INTEGER, "
                    "status TEXT, "
                    "created_at TEXT"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX ix_photo_quarantine_items_project_status_created "
                    "ON photo_quarantine_items (project_id, status, created_at)"
                )
            )

        issues = collect_startup_schema_issues(engine)

        self.assertFalse(
            any(
                "photo_quarantine_items.ix_photo_quarantine_items_project_status_created"
                in issue
                for issue in issues
            ),
            issues,
        )

    def test_collects_alembic_revision_not_head(self):
        engine = self._engine()
        self._bootstrap(engine, revision="026_add_semantic_concepts")

        issues = collect_startup_schema_issues(engine)

        self.assertTrue(any("expected head" in issue for issue in issues), issues)

    def test_validate_startup_schema_reports_aggregated_preflight_failures(self):
        engine = self._engine()
        self._bootstrap(engine, revision="026_add_semantic_concepts")

        with self.assertRaises(StartupSchemaCheckError) as ctx:
            validate_startup_schema(engine)

        msg = str(ctx.exception)
        self.assertIn("missing required tables", msg)
        self.assertIn("expected head", msg)
        self.assertIn("alembic upgrade head", msg)


if __name__ == "__main__":
    unittest.main()
