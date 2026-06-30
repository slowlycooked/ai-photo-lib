from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceEmbedding, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_HUMAN_CONFIRMED,
    STATUS_HUMAN_CORRECTED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .people_learning_service import (
    _has_people_learning_tables,
    _refresh_person_counters,
    match_face_detection_to_person,
)
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
    scope: str = "unknown",
    person_id: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    progress_callback: Optional[Callable[[dict], None]] = None,
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
        .filter(
            FaceDetection.project_id == project_id,
            FaceDetection.status == "embedded",
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
        )
    )

    human_locked_exists = (
        db.query(PersonFaceAssignment.id)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.face_detection_id == FaceDetection.id,
            PersonFaceAssignment.assignment_status.in_(
                [STATUS_HUMAN_CONFIRMED, STATUS_HUMAN_CORRECTED]
            ),
        )
        .exists()
    )
    active_assignment_exists = (
        db.query(PersonFaceAssignment.id)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.face_detection_id == FaceDetection.id,
            PersonFaceAssignment.assignment_status != STATUS_REJECTED,
        )
        .exists()
    )
    cluster_or_pending_exists = (
        db.query(PersonFaceAssignment.id)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.face_detection_id == FaceDetection.id,
            PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            sa.or_(
                PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING,
                PersonFaceAssignment.assignment_source == "unknown_cluster",
            ),
        )
        .exists()
    )

    query = query.filter(~human_locked_exists)
    if scope == "person":
        if person_id is None:
            raise ValueError("person_id is required when scope=person")
        target_person_active_exists = (
            db.query(PersonFaceAssignment.id)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == int(person_id),
                PersonFaceAssignment.face_detection_id == FaceDetection.id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .exists()
        )
        query = query.filter(~target_person_active_exists)
    elif scope == "time_range":
        if start_time is None or end_time is None:
            raise ValueError("start_time and end_time are required when scope=time_range")
        query = query.filter(
            FaceDetection.detected_at.isnot(None),
            FaceDetection.detected_at >= start_time,
            FaceDetection.detected_at <= end_time,
        )
    elif scope == "project":
        pass
    else:
        query = query.filter(sa.or_(~active_assignment_exists, cluster_or_pending_exists))

    query = query.order_by(FaceDetection.id.asc()).limit(max_faces)

    face_ids = [int(row[0]) for row in query.all()]
    matched_faces = 0
    auto_assigned = 0
    review_pending = 0

    for index, face_id in enumerate(face_ids, start=1):
        touched_person_ids: set[int] = set()
        decision = match_face_detection_to_person(
            db,
            project_id=project_id,
            face_detection_id=face_id,
            target_person_id=person_id if scope == "person" else None,
            force_review_pending=scope == "person",
            assignment_source=(
                "targeted_person_rematch" if scope == "person" else "similarity_match"
            ),
        )
        if decision is None:
            continue

        active_assignments = (
            db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.face_detection_id == face_id,
                PersonFaceAssignment.person_id != decision.person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )
        for assignment in active_assignments:
            if assignment.assignment_status in {STATUS_HUMAN_CONFIRMED, STATUS_HUMAN_CORRECTED}:
                continue
            assignment.assignment_status = STATUS_REJECTED
            assignment.assignment_source = "prototype_rematch"
            assignment.is_positive_sample = False
            assignment.is_training_candidate = False
            touched_person_ids.add(int(assignment.person_id))
        for touched_person_id in touched_person_ids:
            _refresh_person_counters(db, project_id=project_id, person_id=touched_person_id)

        matched_faces += 1
        if decision.assignment_status == STATUS_AUTO_ASSIGNED:
            auto_assigned += 1
        elif decision.assignment_status == STATUS_REVIEW_PENDING:
            review_pending += 1

        if progress_callback is not None and (index == len(face_ids) or index % 25 == 0):
            progress_callback(
                {
                    "project_id": project_id,
                    "task_id": None,
                    "status": "running",
                    "running": True,
                    "max_faces": max_faces,
                    "scope": scope,
                    "person_id": person_id,
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                    "faces_considered": index,
                    "matched_faces": matched_faces,
                    "auto_assigned": auto_assigned,
                    "review_pending": review_pending,
                    "errors": 0,
                    "recent_errors": [],
                    "message": f"rematching unknown faces ({index}/{len(face_ids)})",
                }
            )

    db.flush()
    return FaceRematchUnknownResult(
        project_id=project_id,
        faces_considered=len(face_ids),
        matched_faces=matched_faces,
        auto_assigned=auto_assigned,
        review_pending=review_pending,
    )
