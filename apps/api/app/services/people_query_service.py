from __future__ import annotations

from typing import Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceNegativeConstraint, Person, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_HUMAN_CONFIRMED,
    STATUS_HUMAN_CORRECTED,
    STATUS_REVIEW_PENDING,
)
from ..schemas.face import (
    FaceDetectionResponse,
    PersonDetailResponse,
    PersonFaceAssignmentResponse,
    PersonListResponse,
    PersonMatchExplanationResponse,
    PersonReviewListResponse,
    PersonSummaryResponse,
)


class PeopleQueryService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_review_pending(
        self,
        *,
        project_id: int,
        person_id: Optional[int],
        limit: int,
        offset: int,
    ) -> PersonReviewListResponse:
        query = (
            self._db.query(PersonFaceAssignment, FaceDetection)
            .join(
                FaceDetection,
                FaceDetection.id == PersonFaceAssignment.face_detection_id,
            )
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING,
                FaceDetection.project_id == project_id,
            )
        )

        if person_id is not None:
            self._get_person_or_404(project_id, person_id)
            query = query.filter(PersonFaceAssignment.person_id == person_id)

        total = query.count()
        rows = (
            query.order_by(
                PersonFaceAssignment.updated_at.desc(),
                PersonFaceAssignment.id.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        constraints_by_face = self._load_negative_constraints(
            project_id=project_id,
            face_ids=[face_detection.id for _, face_detection in rows],
        )

        return PersonReviewListResponse(
            total=total,
            items=[
                self._serialize_assignment(
                    assignment,
                    face_detection,
                    constraints_by_face=constraints_by_face,
                )
                for assignment, face_detection in rows
            ],
        )

    def list_people(
        self,
        *,
        project_id: int,
        include_unnamed: bool,
        is_named: Optional[bool],
        has_review_pending: Optional[bool],
        min_sample_count: Optional[int],
        min_auto_assigned_count: Optional[int],
        q: Optional[str],
        limit: int,
    ) -> PersonListResponse:
        query = self._db.query(Person).filter(Person.project_id == project_id)

        if is_named is not None:
            query = query.filter(Person.is_named.is_(is_named))
        elif not include_unnamed:
            query = query.filter(Person.is_named.is_(True))

        if has_review_pending is not None:
            if has_review_pending:
                query = query.filter(Person.review_pending_count > 0)
            else:
                query = query.filter(Person.review_pending_count == 0)

        if min_sample_count is not None:
            query = query.filter(Person.sample_count >= min_sample_count)

        if min_auto_assigned_count is not None:
            query = query.filter(Person.auto_assigned_count >= min_auto_assigned_count)

        if q:
            q_term = q.strip()
            if q_term:
                like_term = f"%{q_term}%"
                query = query.filter(
                    sa.or_(
                        Person.display_name.ilike(like_term),
                        Person.normalized_name.ilike(like_term.lower()),
                    )
                )

        total = query.count()
        people = (
            query.order_by(
                Person.is_named.desc(),
                Person.confirmed_sample_count.desc(),
                Person.sample_count.desc(),
                Person.updated_at.desc(),
                Person.id.desc(),
            )
            .limit(limit)
            .all()
        )
        return PersonListResponse(
            total=total,
            items=[PersonSummaryResponse.model_validate(person) for person in people],
        )

    def get_person_detail(
        self,
        *,
        project_id: int,
        person_id: int,
        assignment_limit: int,
    ) -> PersonDetailResponse:
        person = self._get_person_or_404(project_id, person_id)
        base_query = (
            self._db.query(PersonFaceAssignment, FaceDetection)
            .join(
                FaceDetection,
                FaceDetection.id == PersonFaceAssignment.face_detection_id,
            )
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                FaceDetection.project_id == project_id,
            )
        )
        total = (
            self._db.query(PersonFaceAssignment.id)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
            )
            .count()
        )
        rows = (
            base_query
            .order_by(
                PersonFaceAssignment.is_positive_sample.desc(),
                PersonFaceAssignment.updated_at.desc(),
                PersonFaceAssignment.id.desc(),
            )
            .limit(assignment_limit)
            .all()
        )

        constraints_by_face = self._load_negative_constraints(
            project_id=project_id,
            face_ids=[face_detection.id for _, face_detection in rows],
        )

        payload = PersonDetailResponse.model_validate(person)
        payload.assignments = [
            self._serialize_assignment(
                assignment,
                face_detection,
                constraints_by_face=constraints_by_face,
            )
            for assignment, face_detection in rows
        ]
        payload.assignments_total = total
        payload.assignments_limit = assignment_limit
        payload.assignments_has_more = len(rows) < total
        return payload

    def _load_negative_constraints(
        self,
        *,
        project_id: int,
        face_ids: list[int],
    ) -> dict[int, set[int]]:
        unique_face_ids = sorted({int(face_id) for face_id in face_ids})
        if not unique_face_ids:
            return {}
        rows = (
            self._db.query(
                FaceNegativeConstraint.face_detection_id,
                FaceNegativeConstraint.not_person_id,
            )
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id.in_(unique_face_ids),
            )
            .all()
        )
        grouped: dict[int, set[int]] = {}
        for face_id, not_person_id in rows:
            grouped.setdefault(int(face_id), set()).add(int(not_person_id))
        return grouped

    def _get_person_or_404(self, project_id: int, person_id: int) -> Person:
        person = (
            self._db.query(Person)
            .filter(Person.project_id == project_id, Person.id == person_id)
            .first()
        )
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found in project")
        return person

    @staticmethod
    def _serialize_assignment(
        assignment: PersonFaceAssignment,
        face_detection: FaceDetection,
        *,
        constraints_by_face: Optional[dict[int, set[int]]] = None,
    ) -> PersonFaceAssignmentResponse:
        negatives = (constraints_by_face or {}).get(face_detection.id, set())
        negative_count = len(negatives)
        is_human_confirmed = assignment.assignment_status in {
            STATUS_HUMAN_CONFIRMED,
            STATUS_HUMAN_CORRECTED,
        }
        explanation = PersonMatchExplanationResponse(
            similarity=assignment.similarity_score,
            source=assignment.assignment_source,
            is_auto=assignment.assignment_status == STATUS_AUTO_ASSIGNED,
            is_human_confirmed=is_human_confirmed,
            negative_constraint_affected=negative_count > 0,
            negative_constraint_count=negative_count,
        )
        return PersonFaceAssignmentResponse(
            id=assignment.id,
            project_id=assignment.project_id,
            person_id=assignment.person_id,
            face_detection_id=assignment.face_detection_id,
            assignment_status=assignment.assignment_status,
            assignment_source=assignment.assignment_source,
            confidence=assignment.confidence,
            similarity_score=assignment.similarity_score,
            is_positive_sample=assignment.is_positive_sample,
            is_training_candidate=assignment.is_training_candidate,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            explanation=explanation,
            face_detection=FaceDetectionResponse.model_validate(face_detection),
        )
