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
from app.logging_config import (
    photo_id_ctx,
    project_id_ctx,
    setup_logging,
    task_id_ctx,
)
from app.models.ai import AIJob
from app.models.folder import ProjectFolder  # noqa: F401 — registers 'project_folders' table in metadata
from app.models.project_task import ProjectTask  # noqa: F401 — registers 'project_tasks' table in metadata
from app.models.project import Project  # noqa: F401 — registers 'projects' table in metadata
from app.schemas.debug_config import build_default_debug_config
from app.services.aijob_app_service import AIJobAppService
from app.services.project_task_app_service import ProjectTaskAppService
from app.services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)

# ---------------------------------------------------------------------------
setup_logging(build_default_debug_config())
logger = logging.getLogger("worker")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    hide_parameters=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_shutdown = False

# Debug config refresh: only reload every 60 seconds to avoid per-cycle DB hits.
_DEBUG_CONFIG_REFRESH_INTERVAL = 60
_last_debug_config_refresh: float = 0.0
_last_debug_matrix: dict | None = None


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down gracefully…", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Debug config refresh — throttled
# ---------------------------------------------------------------------------


def _maybe_refresh_debug_config(db) -> None:
    global _last_debug_config_refresh, _last_debug_matrix
    now = time.monotonic()
    if now - _last_debug_config_refresh < _DEBUG_CONFIG_REFRESH_INTERVAL:
        return
    _last_debug_config_refresh = now
    try:
        config = RuntimeSettingsService.get_debug_config(db)
        new_matrix = config.debug_matrix.model_dump()
        if new_matrix != _last_debug_matrix:
            setup_logging(config)
            _last_debug_matrix = new_matrix
            logger.debug("worker_debug_config_refreshed matrix=%s", new_matrix)
    except RuntimeSettingsStorageUnavailableError as exc:
        logger.warning("Worker debug config unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Core processing — delegated to AIJobAppService
# ---------------------------------------------------------------------------


def run() -> None:
    logger.info(
        "worker_started model=%s base_url=%s max_retries=%d",
        settings.openai_vision_model,
        settings.openai_base_url,
        settings.ai_max_retries,
    )

    idle_polls: int = 0
    idle_report_interval: int = 6   # report after every 6 × 10 s = 60 s idle

    while not _shutdown:
        try:
            with SessionLocal() as db:
                _maybe_refresh_debug_config(db)

                project_task = (
                    db.query(ProjectTask)
                    .filter(ProjectTask.status == "queued")
                    .order_by(ProjectTask.created_at)
                    .with_for_update(skip_locked=True)
                    .first()
                )

                job = (
                    db.query(AIJob)
                    .filter(AIJob.status == "queued")
                    .order_by(AIJob.created_at)
                    .with_for_update(skip_locked=True)
                    .first()
                )

                if project_task is None and job is None:
                    idle_polls += 1
                    # Emit a single aggregated idle log instead of per-cycle noise
                    if idle_polls % idle_report_interval == 0:
                        logger.debug(
                            "worker_idle polls=%d duration_sec=%d",
                            idle_polls,
                            idle_polls * 10,
                        )
                else:
                    idle_polls = 0

                if project_task is not None and (
                    job is None or project_task.created_at <= job.created_at
                ):
                    tok_proj = project_id_ctx.set(
                        str(project_task.project_id) if project_task.project_id else None
                    )
                    tok_task = task_id_ctx.set(str(project_task.id))
                    tok_photo = photo_id_ctx.set(None)
                    try:
                        ProjectTaskAppService(db).process_task(project_task)
                    finally:
                        project_id_ctx.reset(tok_proj)
                        task_id_ctx.reset(tok_task)
                        photo_id_ctx.reset(tok_photo)
                elif job is not None:
                    tok_proj = project_id_ctx.set(str(job.project_id) if job.project_id else None)
                    tok_task = task_id_ctx.set(str(job.id))
                    tok_photo = photo_id_ctx.set(str(job.photo_id) if job.photo_id else None)
                    try:
                        AIJobAppService(db).process_job(job)
                    finally:
                        project_id_ctx.reset(tok_proj)
                        task_id_ctx.reset(tok_task)
                        photo_id_ctx.reset(tok_photo)
                    continue  # immediately pick next job

                if project_task is not None:
                    continue  # immediately pick next task

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
