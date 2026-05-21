from __future__ import annotations

"""AI Job Application Service (Phase 3).

Encapsulates the full lifecycle of an AI job — analysis and embedding —
so that the worker becomes a thin poller and other callers (e.g. tests,
admin scripts) can reuse the same processing path.

Usage (from worker)::

    service = AIJobAppService(db)
    service.process_job(job)

The ``db`` session must be managed externally (commit / rollback by caller).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.ai import AIJob, PhotoAIAnalysis
from ..models.photo import Photo
from ..services.embedding_client import EmbeddingRequestError
from ..services.embedding_service import upsert_photo_embeddings
from ..services.json_parser import parse_model_json_output
from ..services.project_ai_service import (
    TASK_IMAGE_ANALYSIS,
    analyze_and_parse_with_strict_json_retry,
    get_active_prompt_template,
    get_or_create_project_ai_settings,
    render_analysis_prompt_parts,
)
from ..services.thumbnail import generate_thumbnail
from ..services.vlm_client import VLMRequestError, analyze_image

logger = logging.getLogger(__name__)

_MAX_ERROR_LEN = 12000


class AIJobAppService:
    """Application service that processes a single AI job.

    This service is responsible for:
    * Resolving project AI settings and active prompt template
    * Picking the image path (thumbnail → on-the-fly generation → original)
    * Calling the VLM and parsing the result
    * Writing PhotoAIAnalysis and PhotoEmbedding rows
    * Managing job status transitions (running → success / failed / retry)

    The caller (worker) is responsible for:
    * Selecting and locking the job row (SELECT FOR UPDATE SKIP LOCKED)
    * Committing or rolling back the session after ``process_job`` returns
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── public entry point ────────────────────────────────────────────────────

    def process_job(self, job: AIJob) -> None:
        """Process a single AI job. The job must already be fetched and locked."""
        # Reject jobs without project context — they cannot be processed safely.
        if job.project_id is None:
            self._reject_no_project(job)
            return

        project_id: int = job.project_id

        # Mark running
        now = datetime.now(timezone.utc)
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        self._db.commit()

        photo = (
            self._db.query(Photo)
            .filter(Photo.id == job.photo_id, Photo.project_id == project_id)
            .first()
        )
        if not photo:
            self._fail_missing_photo(job, project_id)
            return

        if job.job_type == "embed":
            self._process_embedding_job(job, photo, project_id)
        else:
            self._process_analysis_job(job, photo, project_id)

    # ── private: reject helpers ───────────────────────────────────────────────

    def _reject_no_project(self, job: AIJob) -> None:
        now = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = (
            f"Job {job.id} has no project_id and cannot be processed. "
            "Re-queue the job with a valid project_id."
        )
        job.finished_at = now
        job.updated_at = now
        self._db.commit()
        logger.error(
            "Job %d rejected: missing project_id (photo_id=%d)", job.id, job.photo_id
        )

    def _fail_missing_photo(self, job: AIJob, project_id: int) -> None:
        now = datetime.now(timezone.utc)
        job.status = "failed"
        job.error_message = f"Photo {job.photo_id} not found in project {project_id}"
        job.finished_at = now
        job.updated_at = now
        self._db.commit()

    # ── private: image path resolution ───────────────────────────────────────

    def _pick_image_path(self, photo: Photo) -> str:
        """Return the path to send to the VLM.

        Priority: existing thumbnail → on-the-fly generation → original file.
        """
        if photo.thumbnail_path and Path(photo.thumbnail_path).exists():
            return photo.thumbnail_path

        new_thumb = generate_thumbnail(photo.file_path, force=True)
        if new_thumb:
            logger.info(
                "Photo %d: generated missing thumbnail on-the-fly: %s",
                photo.id,
                new_thumb,
            )
            photo.thumbnail_path = new_thumb
            self._db.commit()
            return new_thumb

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

    # ── private: analysis job ─────────────────────────────────────────────────

    def _process_analysis_job(
        self, job: AIJob, photo: Photo, project_id: int
    ) -> None:
        try:
            ai_settings = get_or_create_project_ai_settings(self._db, project_id)
            prompt_template = get_active_prompt_template(
                self._db,
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

            image_path = self._pick_image_path(photo)
            logger.info(
                "Analyzing photo. project_id=%d task_id=%d photo_id=%d "
                "file_name=%s prompt_template_id=%s prompt_version=%s image_path=%s",
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
            job.raw_model_output = raw_text[:_MAX_ERROR_LEN]

            # Delete previous analysis (upsert via delete + insert, scoped by project).
            self._db.query(PhotoAIAnalysis).filter(
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
            self._db.add(analysis)
            self._db.flush()

            try:
                upsert_photo_embeddings(
                    self._db,
                    project_id=project_id,
                    photo_id=photo.id,
                    ai=analysis,
                    endpoint_url=ai_settings.endpoint_url,
                )
            except EmbeddingRequestError as exc:
                logger.warning(
                    "Embedding generation failed after analysis. "
                    "project_id=%d task_id=%d photo_id=%d error=%s",
                    project_id,
                    job.id,
                    photo.id,
                    exc,
                )

            photo.status = "ai_indexed"
            photo.updated_at = datetime.now(timezone.utc)

            job.status = "success"
            job.finished_at = datetime.now(timezone.utc)
            job.updated_at = job.finished_at
            job.error_message = None
            job.parse_error = None

            self._db.commit()
            logger.info("Photo %d analyzed successfully.", photo.id)

        except Exception as exc:  # noqa: BLE001
            self._db.rollback()
            self._handle_job_error(job, photo, exc)
            self._db.commit()

    # ── private: embedding job ────────────────────────────────────────────────

    def _process_embedding_job(
        self, job: AIJob, photo: Photo, project_id: int
    ) -> None:
        analysis = (
            self._db.query(PhotoAIAnalysis)
            .filter(
                PhotoAIAnalysis.project_id == project_id,
                PhotoAIAnalysis.photo_id == photo.id,
            )
            .first()
        )
        if not analysis:
            now = datetime.now(timezone.utc)
            job.status = "failed"
            job.error_message = "No AI analysis found"
            job.finished_at = now
            job.updated_at = now
            self._db.commit()
            return

        try:
            ai_settings = get_or_create_project_ai_settings(self._db, project_id)
            upsert_photo_embeddings(
                self._db,
                project_id=project_id,
                photo_id=photo.id,
                ai=analysis,
                endpoint_url=ai_settings.endpoint_url,
            )
            now = datetime.now(timezone.utc)
            job.status = "success"
            job.error_message = None
            job.parse_error = None
            job.finished_at = now
            job.updated_at = now
            self._db.commit()

        except Exception as exc:  # noqa: BLE001
            self._db.rollback()
            is_retryable = not isinstance(exc, EmbeddingRequestError) or exc.retryable
            self._handle_job_error(
                job,
                photo,
                exc,
                is_retryable=is_retryable,
                log_prefix="Embedding job",
            )
            self._db.commit()

    # ── private: error handler ────────────────────────────────────────────────

    def _handle_job_error(
        self,
        job: AIJob,
        photo: Photo,
        exc: Exception,
        *,
        is_retryable: bool | None = None,
        log_prefix: str = "Photo",
    ) -> None:
        if is_retryable is None:
            is_retryable = not isinstance(exc, VLMRequestError) or exc.retryable

        job.retry_count = (job.retry_count or 0) + 1
        error_detail = f"{type(exc).__name__}: {exc}"
        job.error_message = error_detail[:_MAX_ERROR_LEN]
        job.parse_error = error_detail[:_MAX_ERROR_LEN]
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = job.finished_at

        if is_retryable and job.retry_count < global_settings.ai_max_retries:
            job.status = "queued"
            logger.warning(
                "%s %d failed (attempt %d/%d): %s — will retry.",
                log_prefix,
                photo.id,
                job.retry_count,
                global_settings.ai_max_retries,
                exc,
            )
        else:
            job.status = "failed"
            if is_retryable:
                logger.error(
                    "%s %d permanently failed after %d attempts: %s",
                    log_prefix,
                    photo.id,
                    job.retry_count,
                    exc,
                )
            else:
                logger.error(
                    "%s %d failed with a non-retryable error: %s",
                    log_prefix,
                    photo.id,
                    exc,
                )
