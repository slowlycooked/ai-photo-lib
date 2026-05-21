#!/usr/bin/env python3
"""
AI Worker — processes queued ai_jobs, calls llama-server / OpenAI-compatible VLM,
writes results to photo_ai_analysis.

Usage:
    python main.py

Environment variables (see .env.example):
    DATABASE_URL, OPENAI_BASE_URL, OPENAI_MODEL,
    AI_MAX_RETRIES, AI_WORKER_CONCURRENCY, THUMBNAIL_PATH
"""
from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timezone
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
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.logging_config import setup_logging
from app.models.ai import AIJob, PhotoAIAnalysis
from app.models.photo import Photo
from app.models.folder import ProjectFolder  # noqa: F401 — registers 'project_folders' table in metadata
from app.models.project import Project  # noqa: F401 — registers 'projects' table in metadata
from app.schemas.debug_config import build_default_debug_config
from app.services.vlm_client import VLMRequestError, analyze_image
from app.services.json_parser import parse_model_json_output
from app.services.embedding_client import EmbeddingRequestError
from app.services.embedding_service import upsert_photo_embeddings
from app.services.project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    analyze_and_parse_with_strict_json_retry,
    get_active_prompt_template,
    get_or_create_project_ai_settings,
    render_analysis_prompt_parts,
)
from app.services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)
from app.services.thumbnail import generate_thumbnail

# ---------------------------------------------------------------------------
setup_logging(build_default_debug_config())
logger = logging.getLogger("worker")

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_shutdown = False
_MAX_ERROR_MESSAGE_LEN = 12000


def _handle_signal(signum, frame):
    global _shutdown
    logger.info("Received signal %s, shutting down gracefully…", signum)
    _shutdown = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def _pick_image_path(photo: Photo, db: Session) -> str:
    """Return the path to send to the VLM.

    Preference order:
    1. Existing JPEG thumbnail (fast, universal).
    2. On-the-fly thumbnail generation — used when the thumbnail was never
       created (e.g. HEIC file scanned before pillow-heif support was added).
       Persists the result so future jobs skip this step.
    3. Original file path as a last resort (non-HEIC formats only).
    """
    if photo.thumbnail_path and Path(photo.thumbnail_path).exists():
        return photo.thumbnail_path

    # Attempt to generate the thumbnail now (covers HEIC without thumbnails).
    # force=True: if a stale thumbnail file exists for this path it gets overwritten.
    new_thumb = generate_thumbnail(photo.file_path, force=True)
    if new_thumb:
        logger.info(
            "Photo %d: generated missing thumbnail on-the-fly: %s",
            photo.id, new_thumb,
        )
        photo.thumbnail_path = new_thumb
        db.commit()
        return new_thumb

    # Thumbnail generation failed. For HEIC/HEIF we cannot send the raw file
    # to the model — raise a clear, non-retryable error.
    suffix = Path(photo.file_path).suffix.lower()
    if suffix in (".heic", ".heif"):
        raise VLMRequestError(
            f"无法为 HEIC 文件生成缩略图，AI 分析跳过该照片（photo_id={photo.id}）。"
            " 请检查 pillow-heif 安装是否正常后重新扫描。",
            retryable=False,
            code="heic_thumbnail_failed",
        )

    if Path(photo.file_path).exists():
        return photo.file_path

    raise FileNotFoundError(
        f"No accessible image for photo {photo.id}: "
        f"original={photo.file_path!r}, thumbnail={photo.thumbnail_path!r}"
    )


def _process_job(db: Session, job: AIJob) -> None:
    now = datetime.now(timezone.utc)

    # Reject jobs without project context — they cannot be processed safely.
    if job.project_id is None:
        job.status = "failed"
        job.error_message = (
            f"Job {job.id} has no project_id and cannot be processed. "
            "Re-queue the job with a valid project_id."
        )
        job.finished_at = now
        job.updated_at = now
        db.commit()
        logger.error(
            "Job %d rejected: missing project_id (photo_id=%d)",
            job.id,
            job.photo_id,
        )
        return

    project_id: int = job.project_id

    # Mark running
    job.status = "running"
    job.started_at = now
    job.updated_at = now
    db.commit()

    photo = (
        db.query(Photo)
        .filter(Photo.id == job.photo_id, Photo.project_id == project_id)
        .first()
    )
    if not photo:
        job.status = "failed"
        job.error_message = (
            f"Photo {job.photo_id} not found in project {project_id}"
        )
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        db.commit()
        return

    if job.job_type == "embed":
        _process_embedding_job(db, job, photo, project_id)
        return

    try:
        ai_settings = get_or_create_project_ai_settings(db, project_id)
        prompt_template = get_active_prompt_template(
            db,
            project_id,
            task_type=TASK_IMAGE_ANALYSIS,
        )
        system_text, user_text = render_analysis_prompt_parts(
            photo=photo,
            prompt_template=prompt_template,
            output_language=ai_settings.output_language,
        )

        job.prompt_template_id = prompt_template.id
        job.prompt_version = prompt_template.version
        job.model_name = ai_settings.model_name
        job.model_params = {
            "endpoint_url": ai_settings.endpoint_url,
            "temperature": ai_settings.temperature,
            "top_p": ai_settings.top_p,
            "max_tokens": ai_settings.max_tokens,
            "json_parse_strategy": ai_settings.json_parse_strategy,
        }

        image_path = _pick_image_path(photo, db)
        logger.info(
            "Analyzing photo. project_id=%d task_id=%d photo_id=%d file_name=%s prompt_template_id=%s prompt_version=%s image_path=%s",
            project_id,
            job.id,
            photo.id,
            photo.file_name,
            prompt_template.id,
            prompt_template.version,
            image_path,
        )

        raw_text, parsed = analyze_and_parse_with_strict_json_retry(
            analyze_image_fn=analyze_image,
            parse_output_fn=parse_model_json_output,
            image_path=image_path,
            endpoint_url=ai_settings.endpoint_url,
            model_name=ai_settings.model_name,
            system_text=system_text,
            user_text=user_text,
            strategy=ai_settings.json_parse_strategy,
            temperature=ai_settings.temperature,
            top_p=ai_settings.top_p,
            max_tokens=ai_settings.max_tokens,
        )
        job.raw_model_output = raw_text[:_MAX_ERROR_MESSAGE_LEN]

        # Delete previous analysis for this photo in this project (upsert via delete+insert).
        # Scope by both project_id and photo_id to avoid touching other projects.
        db.query(PhotoAIAnalysis).filter(
            PhotoAIAnalysis.project_id == project_id,
            PhotoAIAnalysis.photo_id == photo.id,
        ).delete()

        analysis = PhotoAIAnalysis(
            project_id=project_id,
            photo_id=photo.id,
            model_name=ai_settings.model_name,
            model_version=None,
            caption=parsed.get("caption", ""),
            ocr_text="\n".join(parsed.get("ocr_text", [])),
            scene_tags=parsed.get("scene_tags", []),
            object_tags=parsed.get("object_tags", []),
            activity_tags=parsed.get("activity_tags", []),
            quality_tags=parsed.get("quality_tags", []),
            location_clues=parsed.get("location_clues", []),
            search_keywords=parsed.get("search_keywords", []),
            people_count=parsed.get("people_count", 0),
            confidence=parsed.get("confidence", 0.0),
            raw_result=parsed,
        )
        db.add(analysis)
        db.flush()

        try:
            upsert_photo_embeddings(
                db,
                project_id=project_id,
                photo_id=photo.id,
                ai=analysis,
                endpoint_url=ai_settings.endpoint_url,
            )
        except EmbeddingRequestError as exc:
            logger.warning(
                "Embedding generation failed after analysis. project_id=%d task_id=%d photo_id=%d error=%s",
                project_id,
                job.id,
                photo.id,
                exc,
            )

        # Update photo status
        photo.status = "ai_indexed"
        photo.updated_at = datetime.now(timezone.utc)

        # Mark job success
        job.status = "success"
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        job.error_message = None
        job.parse_error = None

        db.commit()
        logger.info("Photo %d analyzed successfully.", photo.id)

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        is_retryable = not isinstance(exc, VLMRequestError) or exc.retryable
        job.retry_count = (job.retry_count or 0) + 1
        error_detail = f"{type(exc).__name__}: {exc}"
        job.error_message = error_detail[:_MAX_ERROR_MESSAGE_LEN]
        job.parse_error = error_detail[:_MAX_ERROR_MESSAGE_LEN]
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at

        if is_retryable and job.retry_count < settings.ai_max_retries:
            job.status = "queued"
            logger.warning(
                "Photo %d failed (attempt %d/%d): %s — will retry.",
                photo.id if photo else job.photo_id,
                job.retry_count,
                settings.ai_max_retries,
                exc,
            )
        else:
            job.status = "failed"
            if is_retryable:
                logger.error(
                    "Photo %d permanently failed after %d attempts: %s",
                    photo.id if photo else job.photo_id,
                    job.retry_count,
                    exc,
                )
            else:
                logger.error(
                    "Photo %d failed with a non-retryable error: %s",
                    photo.id if photo else job.photo_id,
                    exc,
                )

        db.commit()


def _process_embedding_job(db: Session, job: AIJob, photo: Photo, project_id: int) -> None:
    analysis = (
        db.query(PhotoAIAnalysis)
        .filter(
            PhotoAIAnalysis.project_id == project_id,
            PhotoAIAnalysis.photo_id == photo.id,
        )
        .first()
    )
    if not analysis:
        job.status = "failed"
        job.error_message = "No AI analysis found"
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        db.commit()
        return

    try:
        ai_settings = get_or_create_project_ai_settings(db, project_id)
        upsert_photo_embeddings(
            db,
            project_id=project_id,
            photo_id=photo.id,
            ai=analysis,
            endpoint_url=ai_settings.endpoint_url,
        )
        job.status = "success"
        job.error_message = None
        job.parse_error = None
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if isinstance(exc, EmbeddingRequestError):
            is_retryable = exc.retryable
        else:
            is_retryable = True
        job.retry_count = (job.retry_count or 0) + 1
        error_detail = f"{type(exc).__name__}: {exc}"
        job.error_message = error_detail[:_MAX_ERROR_MESSAGE_LEN]
        job.parse_error = error_detail[:_MAX_ERROR_MESSAGE_LEN]
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at

        if is_retryable and job.retry_count < settings.ai_max_retries:
            job.status = "queued"
            logger.warning(
                "Embedding job failed (attempt %d/%d). project_id=%d task_id=%d photo_id=%d error=%s",
                job.retry_count,
                settings.ai_max_retries,
                project_id,
                job.id,
                photo.id,
                exc,
            )
        else:
            job.status = "failed"
            logger.error(
                "Embedding job permanently failed. project_id=%d task_id=%d photo_id=%d error=%s",
                project_id,
                job.id,
                photo.id,
                exc,
            )

        db.commit()


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
                    _process_job(db, job)
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
