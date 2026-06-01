from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.face import PersonFaceAssignment


class PeopleAssignmentMutationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Optional[PersonFaceAssignment]:
        return (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.face_detection_id == face_id,
            )
            .first()
        )

    def activate(
        self,
        assignment: PersonFaceAssignment,
        *,
        status: str,
        source: str,
        now: datetime,
        confidence: Optional[float],
        similarity_score: Optional[float],
    ) -> None:
        assignment.assignment_status = status
        assignment.assignment_source = source
        assignment.confidence = confidence
        assignment.similarity_score = similarity_score
        assignment.is_positive_sample = True
        assignment.is_training_candidate = True
        assignment.updated_at = now

    def reject(
        self,
        assignment: PersonFaceAssignment,
        *,
        status: str,
        source: str,
        now: datetime,
    ) -> None:
        assignment.assignment_status = status
        assignment.assignment_source = source
        assignment.is_positive_sample = False
        assignment.is_training_candidate = False
        assignment.updated_at = now

    def delete(self, assignment: PersonFaceAssignment) -> None:
        self._db.delete(assignment)
