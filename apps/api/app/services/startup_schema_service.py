from __future__ import annotations

from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


class StartupSchemaCheckError(RuntimeError):
    """Raised when required DB schema objects are missing at startup."""


REQUIRED_TABLES: tuple[str, ...] = (
    "projects",
    "photos",
    "ai_jobs",
    "project_face_settings",
    "face_detections",
    "photo_derivatives",
)


def _read_alembic_revision(engine: Engine) -> str | None:
    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        return None
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()


def validate_required_tables(engine: Engine, required_tables: Iterable[str] = REQUIRED_TABLES) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables = sorted({name for name in required_tables if name not in existing_tables})
    if not missing_tables:
        return

    alembic_revision = _read_alembic_revision(engine)
    missing_text = ", ".join(missing_tables)
    if alembic_revision:
        raise StartupSchemaCheckError(
            "Database schema check failed: missing required tables "
            f"[{missing_text}] while alembic_version is '{alembic_revision}'. "
            "This indicates schema drift (version marked applied but tables are absent). "
            "Run 'alembic upgrade head' to repair migrations."
        )

    raise StartupSchemaCheckError(
        "Database schema check failed: missing required tables "
        f"[{missing_text}] and table 'alembic_version' was not found. "
        "Run 'alembic upgrade head' to initialize and migrate the database."
    )
