from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..face.providers import FaceRecognitionProviderUnavailableError
from ..models.ai import AIJob
from ..schemas.face import FaceScanResponse
from .face_scan_service import FaceScanDisabledError, FaceScanResult, FaceScanService
from .unknown_face_clustering_service import (
    UnknownFaceClusteringResult,
    cluster_unknown_faces,
)


class ManualFaceScanConflictError(RuntimeError):
    pass


class ManualFaceScanProviderUnavailableError(RuntimeError):
    pass


class ManualFaceScanPhotoNotFoundError(RuntimeError):
    pass


class ProjectManualFaceScanAppService:
    def __init__(
        self,
        db: Session,
        *,
        scan_photo_fn: Optional[Callable[[int, int], FaceScanResult]] = None,
        cluster_unknown_faces_fn: Optional[Callable[..., UnknownFaceClusteringResult]] = None,
    ) -> None:
        self._db = db
        self._scan_photo_fn = scan_photo_fn or FaceScanService(db).scan_photo
        self._cluster_unknown_faces_fn = cluster_unknown_faces_fn or cluster_unknown_faces

    def scan_project_photo(self, *, project_id: int, photo_id: int) -> FaceScanResponse:
        started_at = datetime.now(timezone.utc)
        job = AIJob(
            photo_id=photo_id,
            project_id=project_id,
            job_type="face_scan",
            status="running",
            retry_count=0,
            started_at=started_at,
            updated_at=started_at,
        )
        self._db.add(job)
        self._db.commit()

        try:
            result = self._scan_photo_fn(project_id, photo_id)
            response_payload = self._build_response_payload(
                project_id=project_id,
                photo_id=photo_id,
                result=result,
            )
            self._mark_success(job, response_payload)
            return FaceScanResponse.model_validate(response_payload)
        except FaceScanDisabledError as exc:
            self._mark_failed(job, str(exc))
            raise ManualFaceScanConflictError(str(exc)) from exc
        except FaceRecognitionProviderUnavailableError as exc:
            self._mark_failed(job, str(exc))
            raise ManualFaceScanProviderUnavailableError(str(exc)) from exc
        except FileNotFoundError as exc:
            self._mark_failed(job, str(exc))
            raise ManualFaceScanPhotoNotFoundError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            self._mark_failed(job, f"{type(exc).__name__}: {exc}")
            raise

    def _build_response_payload(
        self,
        *,
        project_id: int,
        photo_id: int,
        result: FaceScanResult,
    ) -> dict:
        cluster_assignments_created = 0
        cluster_result = None

        if result.faces_detected > 0:
            cluster_result = self._cluster_unknown_faces_fn(
                self._db,
                project_id=project_id,
                max_faces=max(result.faces_detected, 1),
                photo_ids=[photo_id],
            )
            assignments_created = getattr(cluster_result, "assignments_created", 0)
            if isinstance(assignments_created, int):
                cluster_assignments_created = max(assignments_created, 0)

        response_payload = asdict(result)
        total_review_pending = int(result.review_pending) + cluster_assignments_created
        response_payload["review_pending"] = total_review_pending

        if total_review_pending <= 0 and result.faces_detected > 0:
            skipped_reason = getattr(cluster_result, "skipped_reason", None)
            embedded_ready = int(result.embeddings_created) + int(result.embeddings_updated)
            if skipped_reason == "missing_people_tables":
                response_payload["message"] = (
                    "Face scan completed: review unavailable because required tables "
                    "persons/person_face_assignments are missing. Run alembic upgrade head."
                )
            elif int(result.auto_assigned) > 0:
                response_payload["message"] = (
                    f"Face scan completed: {int(result.auto_assigned)} faces were auto-assigned "
                    "to existing people, so no review_pending entries were created."
                )
            elif embedded_ready <= 0:
                response_payload["message"] = (
                    "Face scan completed: no usable face embeddings were generated "
                    "(common causes: face too small or thumbnail fallback)."
                )
            else:
                response_payload["message"] = (
                    "Face scan completed: no review_pending entries were created for this photo."
                )

        return response_payload

    def _mark_success(self, job: AIJob, response_payload: dict) -> None:
        finished_at = datetime.now(timezone.utc)
        job.status = "success"
        job.error_message = None
        job.parse_error = None
        job.raw_model_output = json.dumps(response_payload, ensure_ascii=True)
        job.finished_at = finished_at
        job.updated_at = finished_at
        self._db.commit()

    def _mark_failed(self, job: AIJob, detail: str) -> None:
        self._db.rollback()
        failed_at = datetime.now(timezone.utc)
        detail_short = detail[:4000]
        job.status = "failed"
        job.error_message = detail_short
        job.parse_error = detail_short
        job.finished_at = failed_at
        job.updated_at = failed_at
        self._db.commit()