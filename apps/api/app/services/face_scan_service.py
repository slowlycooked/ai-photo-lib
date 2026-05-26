from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..face.providers import (
    FaceRecognitionProviderUnavailableError,
    OpenCVFaceProviderConfig,
    OpenCVFaceRecognitionService,
)
from ..face.service import DetectedFace, FaceRecognitionService
from ..models.face import (
    FACE_EMBEDDING_DIMENSION,
    FaceDetection,
    FaceEmbedding,
    ProjectFaceSettings,
)
from ..models.photo import Photo
from ..models.project import Project
from .derivative_service import DerivativeService
from .image_decode_service import read_image_bgr
from .people_learning_service import match_face_detection_to_person
from .project_face_settings_service import get_or_create_project_face_settings


class FaceScanDisabledError(RuntimeError):
    """Raised when a project tries to scan faces while the feature is disabled."""


@dataclass(frozen=True)
class FaceScanResult:
    project_id: int
    photo_id: int
    provider: str
    detector_model: str
    embedding_model: str
    faces_detected: int
    detections_created: int
    detections_updated: int
    embeddings_created: int
    embeddings_updated: int
    auto_assigned: int
    review_pending: int
    failures: int
    message: str
    # Indicates the image source used for this scan
    scan_source: str = "face_work_image"
    # True when the source was a degraded fallback (thumbnail)
    scan_quality_degraded: bool = False


class FaceScanService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def scan_photo(
        self,
        project_id: int,
        photo_id: int,
        *,
        provider: Optional[FaceRecognitionService] = None,
    ) -> FaceScanResult:
        photo = (
            self._db.query(Photo)
            .filter(
                Photo.project_id == project_id,
                Photo.id == photo_id,
                Photo.deleted_at.is_(None),
            )
            .first()
        )
        if photo is None:
            raise FileNotFoundError(f"Photo {photo_id} not found in project {project_id}")

        project = (
            self._db.query(Project)
            .filter(Project.id == project_id, Project.deleted_at.is_(None))
            .first()
        )
        if project is None:
            raise FileNotFoundError(f"Project {project_id} not found")

        settings = get_or_create_project_face_settings(self._db, project_id)
        if not settings.face_recognition_enabled:
            raise FaceScanDisabledError(
                "Face recognition is disabled for this project. Enable it in face settings first."
            )

        resolved_provider = provider or self._resolve_provider(settings)

        # ── Resolve work image ──────────────────────────────────────────────
        # Priority: face_work_image (decoded from original, HEIC-safe)
        # Fallback: ai_thumbnail (degraded quality, detection only, no embedding)
        derivative_svc = DerivativeService(
            self._db,
            thumbnail_root=project.thumbnail_path or global_settings.thumbnail_path,
        )
        image_bgr, scan_source, scan_quality_degraded = self._resolve_work_image(
            photo=photo,
            derivative_svc=derivative_svc,
        )

        detected_faces = resolved_provider.detect_faces_from_bgr(image_bgr)
        work_h, work_w = image_bgr.shape[:2]

        # Re-scan reconciliation uses project-level threshold to avoid introducing
        # a new config field without explicit schema approval.
        reconcile_iou_threshold = max(
            0.0,
            min(1.0, float(settings.min_quality_for_prototype or 0.7)),
        )
        existing_detections = self._list_photo_detections(project_id=project_id, photo_id=photo_id)
        matched_existing_ids: set[int] = set()

        created = 0
        updated = 0
        embedding_created = 0
        embedding_updated = 0
        auto_assigned = 0
        review_pending = 0
        failures = 0

        for detected_face in detected_faces:
            detection, was_created = self._upsert_detection(
                project_id=project_id,
                photo_id=photo_id,
                detected_face=detected_face,
                existing_detections=existing_detections,
                matched_existing_ids=matched_existing_ids,
                iou_threshold=reconcile_iou_threshold,
            )
            if was_created:
                created += 1
            else:
                updated += 1

            try:
                face_size = min(detected_face.bbox.width, detected_face.bbox.height)

                detection.face_quality_score = self._estimate_face_quality(
                    work_w, work_h, detected_face
                )

                if settings.store_face_crops and not scan_quality_degraded:
                    try:
                        crop_result = derivative_svc.create_face_crop(
                            project_id=project_id,
                            photo_id=photo_id,
                            face_detection=detection,
                            source_bgr=image_bgr,
                            source_width=work_w,
                            source_height=work_h,
                        )
                        detection.face_crop_path = crop_result.path
                        detection.face_crop_hash = hashlib.sha256(
                            Path(crop_result.path).read_bytes()
                        ).hexdigest()
                    except Exception as crop_exc:  # noqa: BLE001
                        detection.face_crop_path = None
                        detection.face_crop_hash = None
                        import logging

                        logging.getLogger(__name__).warning(
                            "face_crop save failed for detection %s: %s", detection.id, crop_exc
                        )
                else:
                    detection.face_crop_path = None
                    detection.face_crop_hash = None

                # Project settings own the recognition threshold. The global config
                # only seeds the project default when settings are created.
                min_face_size = settings.min_face_size
                if face_size < min_face_size:
                    detection.status = "too_small_for_recognition"
                    detection.error_message = (
                        f"face_size={face_size} < min_face_size={min_face_size}"
                    )
                    detection.updated_at = datetime.now(timezone.utc)
                    continue

                embedding_result = resolved_provider.embed_face_from_bgr(
                    image_bgr, detected_face
                )
                detection.status = "embedded"
                if scan_quality_degraded:
                    detection.error_message = (
                        "embedded from thumbnail fallback — quality may degrade"
                    )
                else:
                    detection.error_message = None
                detection.updated_at = datetime.now(timezone.utc)

                _, emb_created = self._upsert_embedding(
                    project_id=project_id,
                    detection=detection,
                    embedding_result=embedding_result,
                )
                if not scan_quality_degraded:
                    match_decision = match_face_detection_to_person(
                        self._db,
                        project_id=project_id,
                        face_detection_id=detection.id,
                    )
                    if match_decision is not None:
                        if match_decision.assignment_status == "auto_assigned":
                            auto_assigned += 1
                        elif match_decision.assignment_status == "review_pending":
                            review_pending += 1
                if emb_created:
                    embedding_created += 1
                else:
                    embedding_updated += 1
            except Exception as exc:  # noqa: BLE001
                detection.status = "failed"
                detection.error_message = str(exc)[:4000]
                detection.updated_at = datetime.now(timezone.utc)
                failures += 1

        self._mark_disappeared_detections(
            existing_detections=existing_detections,
            matched_existing_ids=matched_existing_ids,
        )

        self._db.commit()
        return FaceScanResult(
            project_id=project_id,
            photo_id=photo_id,
            provider=settings.face_provider,
            detector_model=settings.face_detector_model,
            embedding_model=settings.face_embedding_model,
            faces_detected=len(detected_faces),
            detections_created=created,
            detections_updated=updated,
            embeddings_created=embedding_created,
            embeddings_updated=embedding_updated,
            auto_assigned=auto_assigned,
            review_pending=review_pending,
            failures=failures,
            message="Face scan completed",
            scan_source=scan_source,
            scan_quality_degraded=scan_quality_degraded,
        )

    def _resolve_work_image(
        self,
        *,
        photo: Photo,
        derivative_svc: DerivativeService,
    ) -> Tuple[np.ndarray, str, bool]:
        """Return (image_bgr, scan_source, quality_degraded).

        Strategy:
        1. Try to build/retrieve a ``face_work_image`` from the original.
        2. On failure (missing source, HEIC decode error, etc.) fall back to
           ``ai_thumbnail`` if it exists on disk.
        3. If nothing is available, raise FileNotFoundError.
        """
        import logging
        _log = logging.getLogger(__name__)

        # ── Primary: face_work_image ────────────────────────────────────────
        try:
            work = derivative_svc.get_or_create_face_work_image(photo)
            image_bgr = read_image_bgr(work.path)
            return image_bgr, "face_work_image", False
        except Exception as primary_exc:  # noqa: BLE001
            _log.warning(
                "face_work_image unavailable for photo_id=%s (project=%s): %s — "
                "attempting thumbnail fallback",
                photo.id,
                photo.project_id,
                primary_exc,
            )

        # ── Fallback: ai_thumbnail ──────────────────────────────────────────
        thumb_path = photo.thumbnail_path
        if thumb_path and Path(thumb_path).exists():
            try:
                image_bgr = read_image_bgr(thumb_path)
                _log.info(
                    "Using thumbnail fallback for face scan of photo_id=%s (project=%s)",
                    photo.id,
                    photo.project_id,
                )
                return image_bgr, "thumbnail_fallback", True
            except Exception as thumb_exc:  # noqa: BLE001
                _log.warning(
                    "Thumbnail fallback also failed for photo_id=%s: %s",
                    photo.id,
                    thumb_exc,
                )

        raise FileNotFoundError(
            f"No readable image available for face scan of photo {photo.id} "
            f"(project {photo.project_id}). "
            f"Original: {photo.file_path}"
        )

    def _resolve_provider(self, settings: ProjectFaceSettings) -> FaceRecognitionService:
        provider_name = (settings.face_provider or "").strip().lower()
        if provider_name == "opencv":
            return OpenCVFaceRecognitionService(
                OpenCVFaceProviderConfig(
                    detector_model=settings.face_detector_model,
                    embedding_model=settings.face_embedding_model,
                    detector_model_path=global_settings.face_detector_model_path,
                    embedding_model_path=global_settings.face_embedding_model_path,
                    min_detection_confidence=settings.min_detection_confidence,
                )
            )
        raise FaceRecognitionProviderUnavailableError(
            f"Unsupported face provider: {settings.face_provider}"
        )

    def _upsert_detection(
        self,
        *,
        project_id: int,
        photo_id: int,
        detected_face: DetectedFace,
        existing_detections: list[FaceDetection],
        matched_existing_ids: set[int],
        iou_threshold: float,
    ) -> Tuple[FaceDetection, bool]:
        bbox = detected_face.bbox
        detection = self._find_reconciled_detection(
            existing_detections=existing_detections,
            matched_existing_ids=matched_existing_ids,
            bbox=(bbox.x, bbox.y, bbox.width, bbox.height),
            iou_threshold=iou_threshold,
        )
        created = detection is None
        if detection is None:
            detection = FaceDetection(
                project_id=project_id,
                photo_id=photo_id,
                bbox_x=bbox.x,
                bbox_y=bbox.y,
                bbox_w=bbox.width,
                bbox_h=bbox.height,
            )
            self._db.add(detection)
            existing_detections.append(detection)
        else:
            detection.bbox_x = bbox.x
            detection.bbox_y = bbox.y
            detection.bbox_w = bbox.width
            detection.bbox_h = bbox.height

        detection.detection_confidence = detected_face.detection_confidence
        detection.detected_at = datetime.now(timezone.utc)
        detection.status = "pending"
        detection.error_message = None
        detection.updated_at = datetime.now(timezone.utc)
        self._db.flush()
        matched_existing_ids.add(detection.id)
        return detection, created

    def _list_photo_detections(self, *, project_id: int, photo_id: int) -> list[FaceDetection]:
        return (
            self._db.query(FaceDetection)
            .filter(
                FaceDetection.project_id == project_id,
                FaceDetection.photo_id == photo_id,
            )
            .order_by(FaceDetection.id.asc())
            .all()
        )

    def _find_reconciled_detection(
        self,
        *,
        existing_detections: list[FaceDetection],
        matched_existing_ids: set[int],
        bbox: tuple[int, int, int, int],
        iou_threshold: float,
    ) -> Optional[FaceDetection]:
        # Exact bbox reuse remains highest priority for strict idempotency.
        for detection in existing_detections:
            if detection.id in matched_existing_ids:
                continue
            if (
                detection.bbox_x == bbox[0]
                and detection.bbox_y == bbox[1]
                and detection.bbox_w == bbox[2]
                and detection.bbox_h == bbox[3]
            ):
                return detection

        best_match: Optional[FaceDetection] = None
        best_iou = -1.0
        for detection in existing_detections:
            if detection.id in matched_existing_ids:
                continue
            iou = self._bbox_iou(
                (detection.bbox_x, detection.bbox_y, detection.bbox_w, detection.bbox_h),
                bbox,
            )
            if iou >= iou_threshold and iou > best_iou:
                best_match = detection
                best_iou = iou
        return best_match

    def _mark_disappeared_detections(
        self,
        *,
        existing_detections: list[FaceDetection],
        matched_existing_ids: set[int],
    ) -> None:
        now = datetime.now(timezone.utc)
        for detection in existing_detections:
            if detection.id in matched_existing_ids:
                continue
            detection.status = "disappeared"
            detection.error_message = "not matched by latest scan"
            detection.updated_at = now

    @staticmethod
    def _bbox_iou(
        bbox_a: tuple[int, int, int, int],
        bbox_b: tuple[int, int, int, int],
    ) -> float:
        ax1, ay1, aw, ah = bbox_a
        bx1, by1, bw, bh = bbox_b
        ax2 = ax1 + max(aw, 0)
        ay2 = ay1 + max(ah, 0)
        bx2 = bx1 + max(bw, 0)
        by2 = by1 + max(bh, 0)

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        intersection = float(inter_w * inter_h)

        area_a = float(max(aw, 0) * max(ah, 0))
        area_b = float(max(bw, 0) * max(bh, 0))
        union = area_a + area_b - intersection
        if union <= 0.0:
            return 0.0
        return intersection / union

    def _upsert_embedding(
        self,
        *,
        project_id: int,
        detection: FaceDetection,
        embedding_result,
    ) -> Tuple[FaceEmbedding, bool]:
        actual_dim = len(embedding_result.vector or [])
        if embedding_result.embedding_dim != actual_dim:
            raise ValueError(
                "Face embedding_dim does not match vector length "
                f"(embedding_dim={embedding_result.embedding_dim}, len(vector)={actual_dim})"
            )
        if actual_dim != FACE_EMBEDDING_DIMENSION:
            raise ValueError(
                "Face embedding dimension mismatch for current schema: "
                f"expected {FACE_EMBEDDING_DIMENSION}, got {actual_dim}. "
                "Check provider model and database migrations."
            )

        row = (
            self._db.query(FaceEmbedding)
            .filter(
                FaceEmbedding.project_id == project_id,
                FaceEmbedding.face_detection_id == detection.id,
                FaceEmbedding.model_name == embedding_result.model_name,
                FaceEmbedding.model_version == (embedding_result.model_version or ""),
            )
            .first()
        )
        created = row is None
        if row is None:
            row = FaceEmbedding(
                project_id=project_id,
                face_detection_id=detection.id,
                model_name=embedding_result.model_name,
                model_version=embedding_result.model_version or "",
            )
            self._db.add(row)

        row.model_provider = embedding_result.model_provider
        row.embedding_dim = actual_dim
        row.embedding_vector = embedding_result.vector
        row.embedding_hash = self._hash_embedding(embedding_result.vector)
        row.embedded_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        self._db.flush()
        return row, created

    def _maybe_store_face_crop(
        self,
        *,
        image_path: Path,
        project: Project,
        detection: FaceDetection,
        detected_face: DetectedFace,
        store_face_crops: bool,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Legacy helper kept for backward compatibility with existing tests.

        New code should use ``DerivativeService.create_face_crop()`` instead.
        """
        if not store_face_crops:
            return None, None

        from PIL import Image as _PilImage
        from .image_decode_service import read_image_pil as _read_pil

        crop_root = Path(project.thumbnail_path or global_settings.thumbnail_path) / "face-crops"
        crop_root.mkdir(parents=True, exist_ok=True)
        crop_path = crop_root / f"project-{project.id}-photo-{detection.photo_id}-face-{detection.id}.jpg"

        with _read_pil(image_path) as image:
            x1, y1, x2, y2 = self._clamp_bbox(
                image.width,
                image.height,
                detected_face,
            )
            crop = image.crop((x1, y1, x2, y2)).convert("RGB")
            crop.save(crop_path, format="JPEG", quality=92)

        crop_hash = hashlib.sha256(crop_path.read_bytes()).hexdigest()
        return str(crop_path), crop_hash

    @staticmethod
    def _clamp_bbox(
        image_width: int,
        image_height: int,
        detected_face: DetectedFace,
    ) -> Tuple[int, int, int, int]:
        bbox = detected_face.bbox
        x1 = max(0, bbox.x)
        y1 = max(0, bbox.y)
        x2 = min(image_width, bbox.x + bbox.width)
        y2 = min(image_height, bbox.y + bbox.height)
        if x2 <= x1:
            x2 = min(image_width, x1 + 1)
        if y2 <= y1:
            y2 = min(image_height, y1 + 1)
        return x1, y1, x2, y2

    @staticmethod
    def _estimate_face_quality(
        image_width: int,
        image_height: int,
        detected_face: DetectedFace,
    ) -> float:
        bbox = detected_face.bbox
        area_ratio = (bbox.width * bbox.height) / float(
            max(image_width, 1) * max(image_height, 1)
        )
        size_score = min(1.0, area_ratio * 12.0)
        confidence = (
            detected_face.detection_confidence
            if detected_face.detection_confidence is not None
            else 0.5
        )
        return round((0.65 * confidence) + (0.35 * size_score), 4)

    @staticmethod
    def _hash_embedding(vector: list[float]) -> str:
        normalized = json.dumps(vector, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
