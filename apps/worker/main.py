#!/usr/bin/env python3
"""
AI Worker — processes queued ai_jobs, calls llama-server / OpenAI-compatible VLM,
writes results to photo_ai_analysis.

Usage:
    python main.py

Environment variables (see .env.example):
    DATABASE_URL, OPENAI_BASE_URL, OPENAI_MODEL,
    AI_MAX_RETRIES, THUMBNAIL_PATH
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Make `app` package importable by adding the project root to sys.path.
# The worker shares models/services with the API.
# ---------------------------------------------------------------------------
_WORKER_DIR = Path(__file__).resolve().parent
_API_DIR = _WORKER_DIR.parent / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.logging_config import setup_logging
from app.models.ai import AIJob
from app.models.folder import ProjectFolder  # noqa: F401 — registers 'project_folders' table in metadata
from app.models.project import Project  # noqa: F401 — registers 'projects' table in metadata
from app.schemas.debug_config import build_default_debug_config
from app.services.aijob_app_service import AIJobAppService
from app.services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)

# ---------------------------------------------------------------------------
setup_logging(build_default_debug_config())
logger = logging.getLogger("worker")

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down gracefully…", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Core processing — delegated to AIJobAppService
# ---------------------------------------------------------------------------


def run() -> None:
    logger.info(
        "Worker started. model=%s base_url=%s max_retries=%d",
        settings.openai_vision_model,
        settings.openai_base_url,
        settings.ai_max_retries,
    )

    while not _shutdown:
        try:
            with SessionLocal() as db:
                try:
                    setup_logging(RuntimeSettingsService.get_debug_config(db))
                except RuntimeSettingsStorageUnavailableError as exc:
                    logger.warning("Worker debug config unavailable: %s", exc)

                job = (
                    db.query(AIJob)
                    .filter(AIJob.status == "queued")
                    .order_by(AIJob.created_at)
                    .with_for_update(skip_locked=True)
                    .first()
                )

                if job is None:
                    pass  # nothing to do this cycle
                else:
                    AIJobAppService(db).process_job(job)
                    continue  # immediately pick next job

        except OperationalError as exc:
            logger.error("Database connection error: %s — retrying in 30s", exc)
            for _ in range(30):
                if _shutdown:
                    break
                time.sleep(1)
            continue

        # No jobs available — sleep briefly before polling again
        for _ in range(10):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    run()

