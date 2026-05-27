from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceEmbedding, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .people_learning_service import _has_people_learning_tables, match_face_detection_to_person
from .project_face_settings_service import get_or_create_project_face_settings


@dataclass(frozen=True)
class FaceRematchUnknownResult:
    project_id: int
    faces_considered: int
    matched_faces: int
    auto_assigned: int
    review_pending: int
    skipped_reason: Optional[str] = None


def rematch_unknown_faces(
    db: Session,
    *,
    project_id: int,
    max_faces: int = 1000,
) -> FaceRematchUnknownResult:
    if not _has_people_learning_tables(db):
        return FaceRematchUnknownResult(
            project_id=project_id,
            faces_considered=0,
            matched_faces=0,
            auto_assigned=0,
            review_pending=0,
            skipped_reason="missing_people_tables",
        )

    settings = get_or_create_project_face_settings(db, project_id)

    query = (
        db.query(FaceDetection.id)
        .join(
            FaceEmbedding,
            sa.and_(
                FaceEmbedding.project_id == FaceDetection.project_id,
                FaceEmbedding.face_detection_id == FaceDetection.id,
            ),
        )
        .outerjoin(
            PersonFaceAssignment,
            sa.and_(
                PersonFaceAssignment.project_id == FaceDetection.project_id,
                PersonFaceAssignment.face_detection_id == FaceDetection.id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            ),
        )
        .filter(
            FaceDetection.project_id == project_id,
            FaceDetection.status == "embedded",
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
            PersonFaceAssignment.id.is_(None),
        )
        .order_by(FaceDetection.id.asc())
        .limit(max_faces)
    )

    face_ids = [int(row[0]) for row in query.all()]
    matched_faces = 0
    auto_assigned = 0
    review_pending = 0

    for face_id in face_ids:
        decision = match_face_detection_to_person(
            db,
            project_id=project_id,
            face_detection_id=face_id,
        )
        if decision is None:
            continue
        matched_faces += 1
        if decision.assignment_status == STATUS_AUTO_ASSIGNED:
            auto_assigned += 1
        elif decision.assignment_status == STATUS_REVIEW_PENDING:
            review_pending += 1

    db.flush()
    return FaceRematchUnknownResult(
        project_id=project_id,
        faces_considered=len(face_ids),
        matched_faces=matched_faces,
        auto_assigned=auto_assigned,
        review_pending=review_pending,
    )
