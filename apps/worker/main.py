#!/usr/bin/env python3
"""
AI Worker — processes queued ai_jobs, calls Ollama MiniCPM-V,
writes results to photo_ai_analysis.

Usage:
    python main.py

Environment variables (see .env.example):
    DATABASE_URL, OLLAMA_BASE_URL, OLLAMA_MODEL,
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
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models.ai import AIJob, PhotoAIAnalysis
from app.models.photo import Photo
from app.services.ollama_client import analyze_image
from app.services.json_parser import parse_model_json_output

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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
# Core processing
# ---------------------------------------------------------------------------

def _pick_image_path(photo: Photo) -> str:
    """Return the original photo path for AI analysis; thumbnail is only a fallback."""
    if Path(photo.file_path).exists():
        return photo.file_path
    if photo.thumbnail_path and Path(photo.thumbnail_path).exists():
        return photo.thumbnail_path
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
        image_path = _pick_image_path(photo)
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
        job.retry_count = (job.retry_count or 0) + 1
        job.error_message = str(exc)[:2000]
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at

        if job.retry_count < settings.ai_max_retries:
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
            logger.error(
                "Photo %d permanently failed after %d attempts: %s",
                photo.id if photo else job.photo_id,
                job.retry_count,
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

        # No jobs available — sleep briefly before polling again
        for _ in range(10):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Worker shut down cleanly.")


if __name__ == "__main__":
    run()
