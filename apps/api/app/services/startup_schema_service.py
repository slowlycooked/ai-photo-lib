from __future__ import annotations

from pathlib import Path
from typing import Iterable

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from ..config import settings
from ..constants.embedding import DB_EMBEDDING_DIMENSION


class StartupSchemaCheckError(RuntimeError):
    """Raised when required DB schema objects are missing at startup."""


REQUIRED_TABLES: tuple[str, ...] = (
    "projects",
    "photos",
    "ai_jobs",
    "photo_ai_analysis",
    "photo_embeddings",
    "project_face_settings",
    "face_detections",
    "face_embeddings",
    "persons",
    "person_face_assignments",
    "person_prototypes",
    "face_negative_constraints",
    "person_cannot_links",
    "photo_derivatives",
    "project_tasks",
)

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "photo_ai_analysis": ("semantic_concepts",),
    "photo_embeddings": (
        "id",
        "project_id",
        "photo_id",
        "caption_embedding",
        "tag_embedding",
        "ocr_embedding",
        "content_embedding",
        "caption_text_hash",
        "tag_text_hash",
        "ocr_text_hash",
        "content_text_hash",
        "embedding_model",
        "embedding_dimension",
        "embedding_input_version",
        "embedding_status",
        "embedding_error",
        "embedded_at",
        "updated_at",
    ),
}

REQUIRED_INDEXES: dict[str, tuple[str, ...]] = {
    "project_tasks": (
        "uq_project_tasks_one_active_scan",
        "uq_project_tasks_one_active_face_cluster",
        "uq_project_tasks_one_active_face_scan",
        "uq_project_tasks_one_active_face_rematch",
    ),
}

VECTOR_DIMENSIONS: dict[str, dict[str, int]] = {
    "photo_embeddings": {
        "caption_embedding": DB_EMBEDDING_DIMENSION,
        "tag_embedding": DB_EMBEDDING_DIMENSION,
        "ocr_embedding": DB_EMBEDDING_DIMENSION,
        "content_embedding": DB_EMBEDDING_DIMENSION,
    },
}


def _read_alembic_revision(engine: Engine) -> str | None:
    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        return None
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()


def _alembic_head_revision() -> str | None:
    api_dir = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        return None
    return heads[0]


def _read_vector_dimension(engine: Engine, table_name: str, column_name: str) -> int | None:
    if engine.dialect.name != "postgresql":
        return None

    with engine.connect() as conn:
        formatted_type = conn.execute(
            text(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = :table_name
                  AND a.attname = :column_name
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY CASE WHEN n.nspname = current_schema() THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).scalar()

    if not formatted_type or not formatted_type.startswith("vector("):
        return None
    try:
        return int(formatted_type.removeprefix("vector(").removesuffix(")"))
    except ValueError:
        return None


def _read_index_definition(engine: Engine, table_name: str, index_name: str) -> str | None:
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE tablename = :table_name
                      AND indexname = :index_name
                    LIMIT 1
                    """
                ),
                {"table_name": table_name, "index_name": index_name},
            ).scalar()
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            return conn.execute(
                text(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE type = 'index'
                      AND tbl_name = :table_name
                      AND name = :index_name
                    """
                ),
                {"table_name": table_name, "index_name": index_name},
            ).scalar()
    return None


def collect_startup_schema_issues(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    issues: list[str] = []
    existing_tables = set(inspector.get_table_names())

    missing_tables = sorted({name for name in REQUIRED_TABLES if name not in existing_tables})
    if missing_tables:
        issues.append(f"missing required tables [{', '.join(missing_tables)}]")

    missing_columns: list[str] = []
    for table_name, expected_cols in REQUIRED_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name in expected_cols:
            if col_name not in existing:
                missing_columns.append(f"{table_name}.{col_name}")
    if missing_columns:
        issues.append(f"missing required columns [{', '.join(sorted(missing_columns))}]")

    missing_indexes: list[str] = []
    invalid_indexes: list[str] = []
    for table_name, expected_indexes in REQUIRED_INDEXES.items():
        if table_name not in existing_tables:
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name in expected_indexes:
            if index_name not in existing:
                missing_indexes.append(f"{table_name}.{index_name}")
                continue
            definition = _read_index_definition(engine, table_name, index_name)
            if definition:
                normalized = definition.upper()
                if "UNIQUE" not in normalized or "WHERE" not in normalized:
                    invalid_indexes.append(f"{table_name}.{index_name}")
    if missing_indexes:
        issues.append(f"missing required indexes [{', '.join(sorted(missing_indexes))}]")
    if invalid_indexes:
        issues.append(
            f"required indexes are not partial unique indexes [{', '.join(sorted(invalid_indexes))}]"
        )

    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            vector_extension = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            ).first()
        if not vector_extension:
            issues.append("pgvector extension 'vector' is missing")

        dimension_mismatches: list[str] = []
        for table_name, columns in VECTOR_DIMENSIONS.items():
            if table_name not in existing_tables:
                continue
            for column_name, expected_dimension in columns.items():
                actual_dimension = _read_vector_dimension(engine, table_name, column_name)
                if actual_dimension != expected_dimension:
                    actual_text = str(actual_dimension) if actual_dimension is not None else "unknown"
                    dimension_mismatches.append(
                        f"{table_name}.{column_name} expected vector({expected_dimension}) got {actual_text}"
                    )
        if dimension_mismatches:
            issues.append(f"embedding vector dimension mismatch [{'; '.join(dimension_mismatches)}]")

    if settings.embedding_dimension != DB_EMBEDDING_DIMENSION:
        issues.append(
            "embedding dimension config mismatch "
            f"[settings.embedding_dimension={settings.embedding_dimension}, "
            f"schema vector dimension={DB_EMBEDDING_DIMENSION}]"
        )

    if "alembic_version" not in existing_tables:
        issues.append("alembic_version table is missing")
    else:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).scalars().all()
        if len(rows) != 1:
            issues.append(f"alembic_version should have exactly one row, got {len(rows)}")
        else:
            head = _alembic_head_revision()
            if head is None:
                issues.append("alembic has multiple or unreadable heads")
            elif rows[0] != head:
                issues.append(f"alembic revision is '{rows[0]}', expected head '{head}'")

    return issues


def validate_startup_schema(engine: Engine) -> None:
    issues = collect_startup_schema_issues(engine)
    if not issues:
        return

    alembic_revision = _read_alembic_revision(engine)
    issue_text = "; ".join(issues)
    if alembic_revision:
        raise StartupSchemaCheckError(
            "Database schema check failed: "
            f"{issue_text} while alembic_version is '{alembic_revision}'. "
            "This indicates schema drift or pending migrations. "
            "Run 'alembic upgrade head' to repair migrations."
        )

    raise StartupSchemaCheckError(
        "Database schema check failed: "
        f"{issue_text}. Run 'alembic upgrade head' to initialize and migrate the database."
    )


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
