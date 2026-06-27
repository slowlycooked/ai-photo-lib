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
import os
import socket
import signal
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Set

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
from app.models.ai import AIJob  # noqa: F401 — registers 'ai_jobs' table in metadata
from app.models.folder import ProjectFolder  # noqa: F401 — registers 'project_folders' table in metadata
from app.models.project_task import ProjectTask  # noqa: F401 — registers 'project_tasks' table in metadata
from app.models.project import Project  # noqa: F401 — registers 'projects' table in metadata
from app.schemas.debug_config import build_default_debug_config
from app.services.aijob_app_service import AIJobAppService
from app.services.project_task_app_service import ProjectTaskAppService
from app.services.embedding_client import close_all as close_all_embedding_clients
from app.services.face_auto_rematch_scheduler import FaceAutoRematchScheduler
from app.services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)
from app.services.task_claim_service import TaskClaimService

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
_last_debug_matrix: Optional[dict] = None
_RECOVERY_SCAN_INTERVAL = 30
_last_recovery_scan: float = 0.0
_last_auto_rematch_scan: float = 0.0


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


def _normalize_worker_concurrency(value: object) -> int:
    try:
        parsed = int(value or 1)
    except (TypeError, ValueError):
        parsed = 1
    return max(1, parsed)


def _process_claimed_task(kind: str, item_id: int) -> None:
    with SessionLocal() as db:
        if kind == "project_task":
            project_task = db.query(ProjectTask).filter(ProjectTask.id == item_id).first()
            if project_task is None:
                logger.warning("claimed_project_task_missing task_id=%s", item_id)
                return
            tok_proj = project_id_ctx.set(
                str(project_task.project_id) if project_task.project_id else None
            )
            tok_task = task_id_ctx.set(str(project_task.id))
            tok_photo = photo_id_ctx.set(None)
            try:
                ProjectTaskAppService(db).process_task(project_task)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception(
                    "Unexpected error processing project task. task_id=%s project_id=%s task_type=%s",
                    project_task.id,
                    project_task.project_id,
                    project_task.task_type,
                )
            finally:
                project_id_ctx.reset(tok_proj)
                task_id_ctx.reset(tok_task)
                photo_id_ctx.reset(tok_photo)
            return

        if kind == "ai_job":
            job = db.query(AIJob).filter(AIJob.id == item_id).first()
            if job is None:
                logger.warning("claimed_ai_job_missing job_id=%s", item_id)
                return
            tok_proj = project_id_ctx.set(str(job.project_id) if job.project_id else None)
            tok_task = task_id_ctx.set(str(job.id))
            tok_photo = photo_id_ctx.set(str(job.photo_id) if job.photo_id else None)
            try:
                AIJobAppService(db).process_job(job)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception(
                    "AI job processing failed. job_id=%s project_id=%s photo_id=%s",
                    job.id,
                    job.project_id,
                    job.photo_id,
                )
            finally:
                project_id_ctx.reset(tok_proj)
                task_id_ctx.reset(tok_task)
                photo_id_ctx.reset(tok_photo)


def _collect_completed_futures(inflight: Set[Future]) -> None:
    completed = [future for future in inflight if future.done()]
    for future in completed:
        inflight.remove(future)
        try:
            future.result()
        except Exception:  # noqa: BLE001
            logger.exception("worker_task_future_failed")


def _maybe_schedule_auto_face_rematch(db) -> None:
    global _last_auto_rematch_scan
    interval = max(60, int(settings.face_auto_rematch_check_interval_seconds or 3600))
    now = time.monotonic()
    if now - _last_auto_rematch_scan < interval:
        return
    _last_auto_rematch_scan = now
    result = FaceAutoRematchScheduler(db).run_once()
    if result.projects_checked or result.tasks_created or result.tasks_reused:
        logger.info(
            "face_auto_rematch_checked projects=%d created=%d reused=%d skipped_recent=%d",
            result.projects_checked,
            result.tasks_created,
            result.tasks_reused,
            result.skipped_recent,
        )


def run() -> None:
    global _last_recovery_scan

    worker_concurrency = _normalize_worker_concurrency(settings.ai_worker_concurrency)
    worker_id = f"worker-{socket.gethostname()}-{os.getpid()}"
    logger.info(
        "worker_started worker_id=%s model=%s base_url=%s max_retries=%d concurrency=%d",
        worker_id,
        settings.openai_vision_model,
        settings.openai_base_url,
        settings.ai_max_retries,
        worker_concurrency,
    )

    idle_polls: int = 0
    idle_report_interval: int = 30
    inflight: Set[Future] = set()
    executor = ThreadPoolExecutor(
        max_workers=worker_concurrency,
        thread_name_prefix="ai-worker",
    )

    try:
        while not _shutdown:
            _collect_completed_futures(inflight)
            available_slots = worker_concurrency - len(inflight)
            claimed_count = 0

            if available_slots > 0:
                try:
                    with SessionLocal() as db:
                        _maybe_refresh_debug_config(db)

                        claim_service = TaskClaimService(db, worker_id=worker_id)
                        now = time.monotonic()
                        if now - _last_recovery_scan >= _RECOVERY_SCAN_INTERVAL:
                            recovered = claim_service.recover_stuck_running_tasks()
                            _last_recovery_scan = now
                            if recovered["project_tasks"] or recovered["ai_jobs"]:
                                logger.warning(
                                    "worker_recovered_stuck_tasks project_tasks=%d ai_jobs=%d",
                                    recovered["project_tasks"],
                                    recovered["ai_jobs"],
                                )
                        _maybe_schedule_auto_face_rematch(db)

                        for _ in range(available_slots):
                            claimed = claim_service.claim_next()
                            if claimed is None:
                                break
                            claimed_count += 1
                            inflight.add(
                                executor.submit(
                                    _process_claimed_task,
                                    claimed.kind,
                                    int(claimed.item.id),
                                )
                            )
                except OperationalError as exc:
                    logger.error("Database connection error: %s — retrying in 30s", exc)
                    for _ in range(30):
                        if _shutdown:
                            break
                        time.sleep(1)
                    continue

            if claimed_count > 0:
                idle_polls = 0
                continue

            if inflight:
                time.sleep(0.2)
                continue

            idle_polls += 1
            if idle_polls % idle_report_interval == 0:
                logger.debug(
                    "worker_idle polls=%d duration_sec=%d",
                    idle_polls,
                    idle_polls,
                )

            if _shutdown:
                break
            time.sleep(1)
    finally:
        executor.shutdown(wait=True)
        close_all_embedding_clients()
        logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    run()
