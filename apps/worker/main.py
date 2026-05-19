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
from app.models.ai import AIJob, PhotoAIAnalysis
from app.models.photo import Photo
from app.models.folder import ProjectFolder  # noqa: F401 — registers 'project_folders' table in metadata
from app.models.project import Project  # noqa: F401 — registers 'projects' table in metadata
from app.services.vlm_client import VLMRequestError, analyze_image
from app.services.json_parser import parse_model_json_output
from app.services.thumbnail import generate_thumbnail

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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

    # Mark running
    job.status = "running"
    job.started_at = now
    job.updated_at = now
    db.commit()

    photo = db.query(Photo).filter(Photo.id == job.photo_id).first()
    if not photo:
        job.status = "failed"
        job.error_message = f"Photo {job.photo_id} not found in database"
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        db.commit()
        return

    try:
        image_path = _pick_image_path(photo, db)
        logger.info("Analyzing photo %d (%s) via %s…", photo.id, photo.file_name, image_path)

        raw_text = analyze_image(image_path)
        parsed = parse_model_json_output(raw_text)

        # Delete previous analysis for this photo (upsert via delete+insert)
        db.query(PhotoAIAnalysis).filter(
            PhotoAIAnalysis.photo_id == photo.id
        ).delete()

        analysis = PhotoAIAnalysis(
            photo_id=photo.id,
            model_name=settings.openai_vision_model,
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

        # Update photo status
        photo.status = "ai_indexed"
        photo.updated_at = datetime.now(timezone.utc)

        # Mark job success
        job.status = "success"
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at
        job.error_message = None

        db.commit()
        logger.info("Photo %d analyzed successfully.", photo.id)

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        is_retryable = not isinstance(exc, VLMRequestError) or exc.retryable
        job.retry_count = (job.retry_count or 0) + 1
        error_detail = f"{type(exc).__name__}: {exc}"
        job.error_message = error_detail[:_MAX_ERROR_MESSAGE_LEN]
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
