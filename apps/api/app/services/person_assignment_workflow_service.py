from __future__ import annotations

from datetime import datetime, timezone
from typing import Collection, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import Person, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_HUMAN_CONFIRMED,
    STATUS_HUMAN_CORRECTED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .people_feedback_effects_service import PeopleFeedbackEffectsService
from .people_assignment_store import PeopleAssignmentStore
from .people_lookup_service import PeopleLookupService
from .people_negative_constraint_service import PeopleNegativeConstraintService
from .people_update_finalizer import PeopleUpdateFinalizer
from .project_face_settings_service import get_or_create_project_face_settings


class PersonAssignmentWorkflowService:
    def __init__(self, db: Session, feedback_effects: PeopleFeedbackEffectsService) -> None:
        self._db = db
        self._assignments = PeopleAssignmentStore(db)
        self._feedback_effects = feedback_effects
        self._finalizer = PeopleUpdateFinalizer(db)
        self._lookup = PeopleLookupService(db)
        self._negative_constraints = PeopleNegativeConstraintService(db)

    def _neg_enabled(self, project_id: int) -> bool:
        """Return True if negative constraints should be written for this project."""
        return get_or_create_project_face_settings(
            self._db, project_id
        ).enable_negative_constraints

    def _reset_feedback_effects(self) -> None:
        self._feedback_effects.reset()

    def _set_feedback_effects(
        self,
        *,
        project_id: int,
        rebuilt_person_ids: Collection[int],
        rematch_scope: Optional[str] = None,
        rematch_person_id: Optional[int] = None,
    ) -> None:
        self._feedback_effects.set(
            project_id=project_id,
            rebuilt_person_ids=rebuilt_person_ids,
            rematch_scope=rematch_scope,
            rematch_person_id=rematch_person_id,
        )

    def confirm_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lookup.get_person_or_404(project_id, person_id)
        self._lookup.get_face_or_404(project_id, face_id)
        assignment = self._assignments.get(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )
        now = datetime.now(timezone.utc)
        if assignment is None:
            assignment = PersonFaceAssignment(
                project_id=project_id,
                person_id=person_id,
                face_detection_id=face_id,
                assignment_status=STATUS_HUMAN_CONFIRMED,
                assignment_source="human_label",
                confidence=1.0,
                similarity_score=None,
                is_positive_sample=True,
                is_training_candidate=True,
                updated_at=now,
            )
            self._db.add(assignment)
        else:
            self._assignments.activate(
                assignment,
                status=STATUS_HUMAN_CONFIRMED,
                source="human_label",
                now=now,
                confidence=assignment.confidence,
                similarity_score=assignment.similarity_score,
            )

        touched_person_ids = {person_id}
        other_assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.face_detection_id == face_id,
                PersonFaceAssignment.person_id != person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )
        for other in other_assignments:
            self._assignments.reject(
                other,
                status=STATUS_REJECTED,
                source="human_corrected",
                now=now,
            )
            touched_person_ids.add(other.person_id)
            if self._neg_enabled(project_id):
                self._negative_constraints.upsert(
                    project_id=project_id,
                    face_id=face_id,
                    not_person_id=other.person_id,
                    source="human_corrected",
                )

        self._negative_constraints.remove(
            project_id=project_id,
            face_id=face_id,
            not_person_id=person_id,
        )
        if person.representative_face_detection_id is None:
            person.representative_face_detection_id = face_id

        self._finalizer.finalize(project_id=project_id, person_ids=touched_person_ids)
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=touched_person_ids,
            rematch_scope="person",
            rematch_person_id=person_id,
        )
        self._db.refresh(person)
        return person

    def exclude_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lookup.get_person_or_404(project_id, person_id)
        self._lookup.get_face_or_404(project_id, face_id)
        assignment = self._assignments.get(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )
        if assignment is None:
            raise HTTPException(status_code=404, detail="Face assignment not found for this person")

        self._assignments.reject(
            assignment,
            status=STATUS_REJECTED,
            source="human_rejected",
            now=datetime.now(timezone.utc),
        )
        if self._neg_enabled(project_id):
            self._negative_constraints.upsert(
                project_id=project_id,
                face_id=face_id,
                not_person_id=person_id,
                source="human_rejected",
            )
        if person.representative_face_detection_id == face_id:
            person.representative_face_detection_id = None

        self._finalizer.finalize(project_id=project_id, person_ids=[person_id])
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[person_id],
            rematch_scope="person",
            rematch_person_id=person_id,
        )
        self._db.refresh(person)
        return person

    def move_face(
        self,
        *,
        project_id: int,
        source_person_id: int,
        face_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person]:
        self._reset_feedback_effects()
        source_person = self._lookup.get_person_or_404(project_id, source_person_id)
        target_person = self._lookup.get_person_or_404(project_id, target_person_id)
        if source_person.id == target_person.id:
            raise HTTPException(status_code=422, detail="target_person_id must be different")

        self._lookup.get_face_or_404(project_id, face_id)
        source_assignment = self._assignments.get(
            project_id=project_id,
            person_id=source_person.id,
            face_id=face_id,
        )
        if source_assignment is None:
            raise HTTPException(status_code=404, detail="Face assignment not found for source person")

        now = datetime.now(timezone.utc)
        confidence = source_assignment.confidence
        similarity_score = source_assignment.similarity_score
        self._assignments.delete(source_assignment)
        target_assignment = self._assignments.get(
            project_id=project_id,
            person_id=target_person.id,
            face_id=face_id,
        )
        if target_assignment is None:
            target_assignment = PersonFaceAssignment(
                project_id=project_id,
                person_id=target_person.id,
                face_detection_id=face_id,
                assignment_status=STATUS_HUMAN_CORRECTED,
                assignment_source="human_move",
                confidence=1.0,
                similarity_score=None,
                is_positive_sample=True,
                is_training_candidate=True,
                updated_at=now,
            )
            self._db.add(target_assignment)
        else:
            self._assignments.activate(
                target_assignment,
                status=STATUS_HUMAN_CORRECTED,
                source="human_move",
                now=now,
                confidence=confidence,
                similarity_score=similarity_score,
            )

        if self._neg_enabled(project_id):
            self._negative_constraints.upsert(
                project_id=project_id,
                face_id=face_id,
                not_person_id=source_person.id,
                source="human_corrected",
            )
        self._negative_constraints.remove(
            project_id=project_id,
            face_id=face_id,
            not_person_id=target_person.id,
        )
        if source_person.representative_face_detection_id == face_id:
            source_person.representative_face_detection_id = None
        if target_person.representative_face_detection_id is None:
            target_person.representative_face_detection_id = face_id

        self._finalizer.finalize(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person

    def set_cover_face(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lookup.get_person_or_404(project_id, person_id)
        self._lookup.get_face_or_404(project_id, face_id)
        assignment = self._assignments.get(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )
        if assignment is None or assignment.assignment_status == STATUS_REJECTED:
            raise HTTPException(
                status_code=422,
                detail="Representative face must be an active assignment of this person",
            )
        person.representative_face_detection_id = face_id
        person.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])
        self._db.refresh(person)
        return person

    def batch_confirm_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        self._reset_feedback_effects()
        person = self._lookup.get_person_or_404(project_id, person_id)
        face_ids = sorted({int(face_id) for face_id in face_detection_ids})
        now = datetime.now(timezone.utc)
        assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING,
            )
            .all()
        )
        if not assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for this person")

        touched_person_ids = {person_id}
        assigned_face_ids = [assignment.face_detection_id for assignment in assignments]
        other_assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.face_detection_id.in_(assigned_face_ids),
                PersonFaceAssignment.person_id != person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )
        other_assignments_by_face_id: dict[int, list[PersonFaceAssignment]] = {}
        for other in other_assignments:
            other_assignments_by_face_id.setdefault(other.face_detection_id, []).append(other)

        for assignment in assignments:
            self._assignments.activate(
                assignment,
                status=STATUS_HUMAN_CONFIRMED,
                source="human_label",
                now=now,
                confidence=assignment.confidence,
                similarity_score=assignment.similarity_score,
            )
            for other in other_assignments_by_face_id.get(assignment.face_detection_id, []):
                self._assignments.reject(
                    other,
                    status=STATUS_REJECTED,
                    source="human_corrected",
                    now=now,
                )
                touched_person_ids.add(other.person_id)
            if person.representative_face_detection_id is None:
                person.representative_face_detection_id = assignment.face_detection_id

        if self._neg_enabled(project_id):
            self._negative_constraints.upsert_many(
                project_id=project_id,
                pairs=[
                    (other.face_detection_id, other.person_id)
                    for other in other_assignments
                ],
                source="human_corrected",
            )
        self._negative_constraints.remove_for_person(
            project_id=project_id,
            face_ids=assigned_face_ids,
            not_person_id=person_id,
        )
        self._finalizer.finalize(project_id=project_id, person_ids=touched_person_ids)
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=touched_person_ids,
            rematch_scope="person",
            rematch_person_id=person_id,
        )
        self._db.refresh(person)
        return person, len(assignments)

    def batch_reject_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        self._reset_feedback_effects()
        person = self._lookup.get_person_or_404(project_id, person_id)
        face_ids = sorted({int(face_id) for face_id in face_detection_ids})
        now = datetime.now(timezone.utc)
        assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING,
            )
            .all()
        )
        if not assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for this person")

        assigned_face_ids = [assignment.face_detection_id for assignment in assignments]
        for assignment in assignments:
            self._assignments.reject(
                assignment,
                status=STATUS_REJECTED,
                source="human_rejected",
                now=now,
            )
            if person.representative_face_detection_id == assignment.face_detection_id:
                person.representative_face_detection_id = None

        if self._neg_enabled(project_id):
            self._negative_constraints.upsert_many(
                project_id=project_id,
                pairs=[(face_id, person_id) for face_id in assigned_face_ids],
                source="human_rejected",
            )
        self._finalizer.finalize(project_id=project_id, person_ids=[person_id])
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[person_id],
            rematch_scope="person",
            rematch_person_id=person_id,
        )
        self._db.refresh(person)
        return person, len(assignments)

    def batch_move_review_pending(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, Person, int]:
        self._reset_feedback_effects()
        source_person = self._lookup.get_person_or_404(project_id, source_person_id)
        target_person = self._lookup.get_person_or_404(project_id, target_person_id)
        if source_person.id == target_person.id:
            raise HTTPException(status_code=422, detail="target_person_id must be different")

        face_ids = sorted({int(face_id) for face_id in face_detection_ids})
        now = datetime.now(timezone.utc)
        source_assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == source_person.id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING,
            )
            .all()
        )
        if not source_assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for source person")

        assigned_face_ids = [assignment.face_detection_id for assignment in source_assignments]
        target_assignments = {
            assignment.face_detection_id: assignment
            for assignment in (
                self._db.query(PersonFaceAssignment)
                .filter(
                    PersonFaceAssignment.project_id == project_id,
                    PersonFaceAssignment.person_id == target_person.id,
                    PersonFaceAssignment.face_detection_id.in_(assigned_face_ids),
                )
                .all()
            )
        }
        updated = 0
        for source_assignment in source_assignments:
            face_detection_id = source_assignment.face_detection_id
            confidence = source_assignment.confidence
            similarity_score = source_assignment.similarity_score
            self._assignments.delete(source_assignment)
            target_assignment = target_assignments.get(face_detection_id)
            if target_assignment is None:
                target_assignment = PersonFaceAssignment(
                    project_id=project_id,
                    person_id=target_person.id,
                    face_detection_id=face_detection_id,
                    assignment_status=STATUS_HUMAN_CORRECTED,
                    assignment_source="human_move",
                    confidence=confidence,
                    similarity_score=None,
                    is_positive_sample=True,
                    is_training_candidate=True,
                    updated_at=now,
                )
                self._db.add(target_assignment)
            else:
                self._assignments.activate(
                    target_assignment,
                    status=STATUS_HUMAN_CORRECTED,
                    source="human_move",
                    now=now,
                    confidence=confidence,
                    similarity_score=similarity_score,
                )

            if source_person.representative_face_detection_id == face_detection_id:
                source_person.representative_face_detection_id = None
            if target_person.representative_face_detection_id is None:
                target_person.representative_face_detection_id = face_detection_id
            updated += 1

        if self._neg_enabled(project_id):
            self._negative_constraints.upsert_many(
                project_id=project_id,
                pairs=[(face_id, source_person.id) for face_id in assigned_face_ids],
                source="human_corrected",
            )
        self._negative_constraints.remove_for_person(
            project_id=project_id,
            face_ids=assigned_face_ids,
            not_person_id=target_person.id,
        )
        self._finalizer.finalize(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person, updated
