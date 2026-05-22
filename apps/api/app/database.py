from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_sql_logger = logging.getLogger("app.database.slow_query")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    hide_parameters=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Slow-query hook — replaces SQLAlchemy DEBUG row logging
# ---------------------------------------------------------------------------

@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_times = conn.info.get("query_start_time")
    if not start_times:
        return
    elapsed_ms = (time.perf_counter() - start_times.pop()) * 1000

    # Determine threshold based on active log level
    if _sql_logger.isEnabledFor(5):        # TRACE → 100 ms
        threshold_ms = 100
    elif _sql_logger.isEnabledFor(logging.DEBUG):  # DEBUG → 300 ms
        threshold_ms = 300
    else:                                  # INFO/WARNING → 1000 ms
        threshold_ms = 1000

    if elapsed_ms >= threshold_ms:
        # Extract first word after SELECT/INSERT/UPDATE/DELETE for table hint
        import re as _re
        table_hint = ""
        m = _re.search(r"(?:FROM|INTO|UPDATE)\s+[\"']?(\w+)", statement, _re.I)
        if m:
            table_hint = f" table={m.group(1)}"
        _sql_logger.warning(
            "slow_query duration_ms=%.1f%s",
            elapsed_ms,
            table_hint,
            extra={"duration_ms": elapsed_ms},
        )


@event.listens_for(engine, "handle_error")
def _handle_error(exception_context):
    _sql_logger.error(
        "sql_error %s",
        exception_context.original_exception,
    )


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
