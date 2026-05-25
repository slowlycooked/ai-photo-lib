from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..models.ai import AIJob
from ..models.derivative import PhotoDerivative
from ..models.face import FaceDetection
from ..models.photo import Photo
from ..repositories.unit_of_work import UnitOfWork
from ..services.project_face_settings_service import get_or_create_project_face_settings


@dataclass(frozen=True)
class FaceScanBatchPlan:
    project_id: int
    scope: str
    total_photos: int
    candidate_photo_ids: list[int]
    candidate_count: int
    skipped_active: int
    skipped_already_scanned: int
    skipped_other_project: int
    stale_count: int
    failed_count: int


@dataclass(frozen=True)
class FaceScanBatchEnqueueResult:
    created_jobs: int
    skipped_active: int


class FaceScanBatchService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def plan(
        self,
        project_id: int,
        *,
        scope: str,
        photo_ids: list[int],
        force: bool,
    ) -> FaceScanBatchPlan:
        settings = get_or_create_project_face_settings(self._db, project_id)

        active_photo_ids = {
            row[0]
            for row in (
                self._db.query(AIJob.photo_id)
                .filter(
                    AIJob.project_id == project_id,
                    AIJob.job_type == "face_scan",
                    AIJob.status.in_(["queued", "running"]),
                )
                .distinct()
                .all()
            )
        }

        project_photo_ids = [
            row[0]
            for row in (
                self._db.query(Photo.id)
                .filter(
                    Photo.project_id == project_id,
                    Photo.deleted_at.is_(None),
                )
                .order_by(Photo.id.asc())
                .all()
            )
        ]
        project_photo_id_set = set(project_photo_ids)

        face_detection_photo_ids = {
            row[0]
            for row in (
                self._db.query(FaceDetection.photo_id)
                .filter(FaceDetection.project_id == project_id)
                .distinct()
                .all()
            )
        }

        failed_photo_ids = {
            row[0]
            for row in (
                self._db.query(FaceDetection.photo_id)
                .filter(
                    FaceDetection.project_id == project_id,
                    FaceDetection.status == "failed",
                )
                .distinct()
                .all()
            )
        }
        failed_photo_ids.update(
            row[0]
            for row in (
                self._db.query(AIJob.photo_id)
                .filter(
                    AIJob.project_id == project_id,
                    AIJob.job_type == "face_scan",
                    AIJob.status == "failed",
                )
                .distinct()
                .all()
            )
        )

        stale_photo_ids = self._compute_stale_photo_ids(
            project_id=project_id,
            settings_updated_at=settings.updated_at,
            face_detection_photo_ids=face_detection_photo_ids,
        )

        effective_scope = "all" if force else scope
        skipped_other_project = 0
        selected_valid_photo_ids: list[int] = []

        if effective_scope == "all":
            scoped_photo_ids = project_photo_ids
            skipped_already_scanned = 0
        elif effective_scope == "missing":
            scoped_photo_ids = [
                photo_id
                for photo_id in project_photo_ids
                if photo_id not in face_detection_photo_ids
            ]
            skipped_already_scanned = len(project_photo_ids) - len(scoped_photo_ids)
        elif effective_scope == "failed":
            scoped_photo_ids = [
                photo_id for photo_id in project_photo_ids if photo_id in failed_photo_ids
            ]
            skipped_already_scanned = 0
        elif effective_scope == "stale":
            scoped_photo_ids = [
                photo_id for photo_id in project_photo_ids if photo_id in stale_photo_ids
            ]
            skipped_already_scanned = 0
        else:
            selected_valid_photo_ids = list(dict.fromkeys(photo_ids))
            scoped_photo_ids = [
                photo_id for photo_id in selected_valid_photo_ids if photo_id in project_photo_id_set
            ]
            skipped_other_project = len(selected_valid_photo_ids) - len(scoped_photo_ids)
            skipped_already_scanned = 0

        candidate_photo_ids = [
            photo_id for photo_id in scoped_photo_ids if photo_id not in active_photo_ids
        ]
        skipped_active = len(scoped_photo_ids) - len(candidate_photo_ids)

        return FaceScanBatchPlan(
            project_id=project_id,
            scope=effective_scope,
            total_photos=len(project_photo_ids),
            candidate_photo_ids=candidate_photo_ids,
            candidate_count=len(candidate_photo_ids),
            skipped_active=skipped_active,
            skipped_already_scanned=skipped_already_scanned,
            skipped_other_project=skipped_other_project,
            stale_count=len(stale_photo_ids),
            failed_count=len(failed_photo_ids),
        )

    def enqueue(self, plan: FaceScanBatchPlan) -> FaceScanBatchEnqueueResult:
        uow = UnitOfWork(self._db)
        created_jobs, skipped_active_at_enqueue = uow.ai_jobs.enqueue_bulk_unique(
            plan.project_id,
            plan.candidate_photo_ids,
            job_type="face_scan",
        )
        uow.commit()
        return FaceScanBatchEnqueueResult(
            created_jobs=len(created_jobs),
            skipped_active=plan.skipped_active + len(skipped_active_at_enqueue),
        )

    def status(self, project_id: int) -> dict[str, int]:
        rows = (
            self._db.query(AIJob.status, sa.func.count(AIJob.id))
            .filter(
                AIJob.project_id == project_id,
                AIJob.job_type == "face_scan",
            )
            .group_by(AIJob.status)
            .all()
        )
        return {status: int(count) for status, count in rows}

    def _compute_stale_photo_ids(
        self,
        *,
        project_id: int,
        settings_updated_at,
        face_detection_photo_ids: set[int],
    ) -> set[int]:
        stale_photo_ids: set[int] = set()
        if settings_updated_at is not None:
            for photo_id in face_detection_photo_ids:
                detection_updated_at = (
                    self._db.query(sa.func.max(FaceDetection.updated_at))
                    .filter(
                        FaceDetection.project_id == project_id,
                        FaceDetection.photo_id == photo_id,
                    )
                    .scalar()
                )
                if detection_updated_at is not None and detection_updated_at < settings_updated_at:
                    stale_photo_ids.add(photo_id)

        photos = (
            self._db.query(Photo)
            .filter(Photo.project_id == project_id, Photo.deleted_at.is_(None))
            .all()
        )
        for photo in photos:
            derivative = (
                self._db.query(PhotoDerivative)
                .filter(
                    PhotoDerivative.project_id == project_id,
                    PhotoDerivative.photo_id == photo.id,
                    PhotoDerivative.kind == "face_work_image",
                )
                .first()
            )
            if derivative is None:
                continue
            derivative_path = Path(derivative.path) if derivative.path else None
            source_path = Path(derivative.source_path) if derivative.source_path else None
            derivative_missing = derivative_path is None or not derivative_path.exists()
            source_missing = source_path is None or not source_path.exists()
            source_mtime_changed = False
            if not source_missing and derivative.source_mtime is not None:
                try:
                    source_mtime_changed = float(derivative.source_mtime) != source_path.stat().st_mtime
                except OSError:
                    source_mtime_changed = True
            if (
                derivative.status != "ready"
                or derivative_missing
                or source_missing
                or source_mtime_changed
            ):
                stale_photo_ids.add(photo.id)
        return stale_photo_ids