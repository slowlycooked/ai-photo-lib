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

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "photo_ai_analysis": ("semantic_concepts",),
}


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


def validate_required_columns(
    engine: Engine,
    required_columns: dict[str, tuple[str, ...]] = REQUIRED_COLUMNS,
) -> None:
    inspector = inspect(engine)
    missing_columns: list[str] = []

    for table_name, expected_cols in required_columns.items():
        if not inspector.has_table(table_name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name in expected_cols:
            if col_name not in existing:
                missing_columns.append(f"{table_name}.{col_name}")

    if not missing_columns:
        return

    alembic_revision = _read_alembic_revision(engine)
    missing_text = ", ".join(sorted(missing_columns))
    if alembic_revision:
        raise StartupSchemaCheckError(
            "Database schema check failed: missing required columns "
            f"[{missing_text}] while alembic_version is '{alembic_revision}'. "
            "This indicates schema drift (version marked applied but columns are absent). "
            "Run schema repair (for example: alembic upgrade head or manual ALTER TABLE) to restore required columns."
        )

    raise StartupSchemaCheckError(
        "Database schema check failed: missing required columns "
        f"[{missing_text}] and table 'alembic_version' was not found. "
        "Run 'alembic upgrade head' to initialize and migrate the database."
    )
