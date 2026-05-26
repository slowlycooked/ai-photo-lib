from __future__ import annotations

from datetime import datetime, timezone
from typing import Collection, Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceNegativeConstraint, Person, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_HUMAN_CONFIRMED,
    STATUS_HUMAN_CORRECTED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .people_learning_service import rebuild_person_centroid_prototype


class PeopleMutationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_person(
        self,
        *,
        project_id: int,
        display_name: Optional[str],
        is_named: bool,
    ) -> Person:
        now = datetime.now(timezone.utc)
        resolved_display_name = (display_name or "").strip()
        if not resolved_display_name:
            resolved_display_name = f"Person {now.strftime('%Y%m%d%H%M%S')}"

        resolved_is_named = bool(is_named and resolved_display_name)
        person = Person(
            project_id=project_id,
            display_name=resolved_display_name,
            normalized_name=resolved_display_name.lower() if resolved_is_named else None,
            is_named=resolved_is_named,
            representative_face_detection_id=None,
            sample_count=0,
            confirmed_sample_count=0,
            auto_assigned_count=0,
            review_pending_count=0,
            created_by="human_created",
            updated_at=now,
        )
        self._db.add(person)
        self._db.commit()
        self._db.refresh(person)
        return person

    def rename_person(
        self,
        *,
        project_id: int,
        person_id: int,
        display_name: str,
    ) -> Person:
        person = self._get_person_or_404(project_id, person_id)
        resolved_display_name = display_name.strip()
        if not resolved_display_name:
            raise HTTPException(status_code=422, detail="display_name cannot be empty")
        person.display_name = resolved_display_name
        person.normalized_name = resolved_display_name.lower()
        person.is_named = True
        person.updated_at = datetime.now(timezone.utc)
        self._db.commit()
        self._db.refresh(person)
        return person

    def delete_person(
        self,
        *,
        project_id: int,
        person_id: int,
    ) -> None:
        person = self._get_person_or_404(project_id, person_id)
        active_assignment_count = (
            self._db.query(sa.func.count(PersonFaceAssignment.id))
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .scalar()
            or 0
        )
        if int(active_assignment_count) > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot delete person with active assignments. "
                    "Move or reject active faces first."
                ),
            )

        (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.not_person_id == person_id,
            )
            .delete(synchronize_session=False)
        )
        (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
            )
            .delete(synchronize_session=False)
        )
        self._db.delete(person)
        self._db.commit()

    def merge_people(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person, int]:
        source_person = self._get_person_or_404(project_id, source_person_id)
        target_person = self._get_person_or_404(project_id, target_person_id)
        if source_person.id == target_person.id:
            raise HTTPException(status_code=422, detail="target_person_id must be different")

        now = datetime.now(timezone.utc)
        source_assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == source_person.id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )

        moved_assignments = 0
        for assignment in source_assignments:
            target_assignment = self._get_assignment(
                project_id=project_id,
                person_id=target_person.id,
                face_id=assignment.face_detection_id,
            )
            if target_assignment is None:
                assignment.person_id = target_person.id
                assignment.assignment_source = "human_merge"
                assignment.updated_at = now
                moved_assignments += 1
                continue

            if target_assignment.assignment_status == STATUS_REJECTED:
                target_assignment.assignment_status = assignment.assignment_status
                target_assignment.assignment_source = "human_merge"
                target_assignment.confidence = assignment.confidence
                target_assignment.similarity_score = assignment.similarity_score
                target_assignment.is_positive_sample = assignment.is_positive_sample
                target_assignment.is_training_candidate = assignment.is_training_candidate
                target_assignment.updated_at = now

            self._delete_assignment(assignment)

        if target_person.representative_face_detection_id is None:
            target_person.representative_face_detection_id = source_person.representative_face_detection_id
        source_person.representative_face_detection_id = None
        source_person.updated_at = now
        target_person.updated_at = now

        self._finalize_people_updates(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person, moved_assignments

    def split_person(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        new_display_name: Optional[str],
    ) -> tuple[Person, Person, int]:
        source_person = self._get_person_or_404(project_id, person_id)
        now = datetime.now(timezone.utc)
        face_ids = sorted({int(face_id) for face_id in face_detection_ids})
        source_assignments = (
            self._db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == source_person.id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )
        if not source_assignments:
            raise HTTPException(status_code=404, detail="No active assignments found for split")

        resolved_display_name = (new_display_name or "").strip()
        if not resolved_display_name:
            resolved_display_name = f"Split Person {now.strftime('%Y%m%d%H%M%S')}"

        target_person = Person(
            project_id=project_id,
            display_name=resolved_display_name,
            normalized_name=resolved_display_name.lower(),
            is_named=True,
            representative_face_detection_id=None,
            sample_count=0,
            confirmed_sample_count=0,
            auto_assigned_count=0,
            review_pending_count=0,
            created_by="human_split",
            updated_at=now,
        )
        self._db.add(target_person)
        self._db.flush()

        moved_assignments = 0
        for source_assignment in source_assignments:
            face_detection_id = source_assignment.face_detection_id
            confidence = source_assignment.confidence
            similarity_score = source_assignment.similarity_score
            self._delete_assignment(source_assignment)
            target_assignment = self._get_assignment(
                project_id=project_id,
                person_id=target_person.id,
                face_id=face_detection_id,
            )
            if target_assignment is None:
                target_assignment = PersonFaceAssignment(
                    project_id=project_id,
                    person_id=target_person.id,
                    face_detection_id=face_detection_id,
                    assignment_status=STATUS_HUMAN_CORRECTED,
                    assignment_source="human_split",
                    confidence=confidence,
                    similarity_score=similarity_score,
                    is_positive_sample=True,
                    is_training_candidate=True,
                    updated_at=now,
                )
                self._db.add(target_assignment)
            else:
                self._activate_assignment(
                    target_assignment,
                    status=STATUS_HUMAN_CORRECTED,
                    source="human_split",
                    now=now,
                    confidence=target_assignment.confidence,
                    similarity_score=target_assignment.similarity_score,
                )

            self._upsert_negative_constraint(
                project_id=project_id,
                face_id=face_detection_id,
                not_person_id=source_person.id,
                source="human_split",
            )
            self._remove_negative_constraint(
                project_id=project_id,
                face_id=face_detection_id,
                not_person_id=target_person.id,
            )
            if target_person.representative_face_detection_id is None:
                target_person.representative_face_detection_id = face_detection_id
            if source_person.representative_face_detection_id == face_detection_id:
                source_person.representative_face_detection_id = None
            moved_assignments += 1

        source_person.updated_at = now
        target_person.updated_at = now

        self._finalize_people_updates(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person, moved_assignments

    def confirm_face_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        person = self._get_person_or_404(project_id, person_id)
        self._get_face_or_404(project_id, face_id)
        assignment = self._get_assignment(
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
            self._activate_assignment(
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
            self._reject_assignment(
                other,
                status=STATUS_REJECTED,
                source="human_corrected",
                now=now,
            )
            touched_person_ids.add(other.person_id)
            self._upsert_negative_constraint(
                project_id=project_id,
                face_id=face_id,
                not_person_id=other.person_id,
                source="human_corrected",
            )

        self._remove_negative_constraint(
            project_id=project_id,
            face_id=face_id,
            not_person_id=person_id,
        )
        if person.representative_face_detection_id is None:
            person.representative_face_detection_id = face_id

        self._finalize_people_updates(project_id=project_id, person_ids=touched_person_ids)
        self._db.commit()
        self._db.refresh(person)
        return person

    def reject_face_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        person = self._get_person_or_404(project_id, person_id)
        self._get_face_or_404(project_id, face_id)
        assignment = self._get_assignment(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )
        if assignment is None:
            raise HTTPException(status_code=404, detail="Face assignment not found for this person")

        self._reject_assignment(
            assignment,
            status=STATUS_REJECTED,
            source="human_rejected",
            now=datetime.now(timezone.utc),
        )
        self._upsert_negative_constraint(
            project_id=project_id,
            face_id=face_id,
            not_person_id=person_id,
            source="human_rejected",
        )
        if person.representative_face_detection_id == face_id:
            person.representative_face_detection_id = None

        self._finalize_people_updates(project_id=project_id, person_ids=[person_id])
        self._db.commit()
        self._db.refresh(person)
        return person

    def move_face_assignment(
        self,
        *,
        project_id: int,
        source_person_id: int,
        face_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person]:
        source_person = self._get_person_or_404(project_id, source_person_id)
        target_person = self._get_person_or_404(project_id, target_person_id)
        if source_person.id == target_person.id:
            raise HTTPException(status_code=422, detail="target_person_id must be different")

        self._get_face_or_404(project_id, face_id)
        source_assignment = self._get_assignment(
            project_id=project_id,
            person_id=source_person.id,
            face_id=face_id,
        )
        if source_assignment is None:
            raise HTTPException(status_code=404, detail="Face assignment not found for source person")

        now = datetime.now(timezone.utc)
        confidence = source_assignment.confidence
        similarity_score = source_assignment.similarity_score
        self._delete_assignment(source_assignment)
        target_assignment = self._get_assignment(
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
            self._activate_assignment(
                target_assignment,
                status=STATUS_HUMAN_CORRECTED,
                source="human_move",
                now=now,
                confidence=confidence,
                similarity_score=similarity_score,
            )

        self._upsert_negative_constraint(
            project_id=project_id,
            face_id=face_id,
            not_person_id=source_person.id,
            source="human_corrected",
        )
        self._remove_negative_constraint(
            project_id=project_id,
            face_id=face_id,
            not_person_id=target_person.id,
        )
        if source_person.representative_face_detection_id == face_id:
            source_person.representative_face_detection_id = None
        if target_person.representative_face_detection_id is None:
            target_person.representative_face_detection_id = face_id

        self._finalize_people_updates(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person

    def set_representative_face(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        person = self._get_person_or_404(project_id, person_id)
        self._get_face_or_404(project_id, face_id)
        assignment = self._get_assignment(
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
        self._db.refresh(person)
        return person

    def batch_confirm_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        person = self._get_person_or_404(project_id, person_id)
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
            self._activate_assignment(
                assignment,
                status=STATUS_HUMAN_CONFIRMED,
                source="human_label",
                now=now,
                confidence=assignment.confidence,
                similarity_score=assignment.similarity_score,
            )
            for other in other_assignments_by_face_id.get(assignment.face_detection_id, []):
                self._reject_assignment(
                    other,
                    status=STATUS_REJECTED,
                    source="human_corrected",
                    now=now,
                )
                touched_person_ids.add(other.person_id)
            if person.representative_face_detection_id is None:
                person.representative_face_detection_id = assignment.face_detection_id

        self._upsert_negative_constraints(
            project_id=project_id,
            pairs=[
                (other.face_detection_id, other.person_id)
                for other in other_assignments
            ],
            source="human_corrected",
        )
        self._remove_negative_constraints_for_person(
            project_id=project_id,
            face_ids=assigned_face_ids,
            not_person_id=person_id,
        )
        self._finalize_people_updates(project_id=project_id, person_ids=touched_person_ids)
        self._db.commit()
        self._db.refresh(person)
        return person, len(assignments)

    def batch_reject_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        person = self._get_person_or_404(project_id, person_id)
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
            self._reject_assignment(
                assignment,
                status=STATUS_REJECTED,
                source="human_rejected",
                now=now,
            )
            if person.representative_face_detection_id == assignment.face_detection_id:
                person.representative_face_detection_id = None

        self._upsert_negative_constraints(
            project_id=project_id,
            pairs=[(face_id, person_id) for face_id in assigned_face_ids],
            source="human_rejected",
        )
        self._finalize_people_updates(project_id=project_id, person_ids=[person_id])
        self._db.commit()
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
        source_person = self._get_person_or_404(project_id, source_person_id)
        target_person = self._get_person_or_404(project_id, target_person_id)
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
            self._delete_assignment(source_assignment)
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
                self._activate_assignment(
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

        self._upsert_negative_constraints(
            project_id=project_id,
            pairs=[(face_id, source_person.id) for face_id in assigned_face_ids],
            source="human_corrected",
        )
        self._remove_negative_constraints_for_person(
            project_id=project_id,
            face_ids=assigned_face_ids,
            not_person_id=target_person.id,
        )
        self._finalize_people_updates(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person, updated

    def _get_person_or_404(self, project_id: int, person_id: int) -> Person:
        person = (
            self._db.query(Person)
            .filter(Person.project_id == project_id, Person.id == person_id)
            .first()
        )
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found in project")
        return person

    def _get_face_or_404(self, project_id: int, face_id: int) -> FaceDetection:
        face = (
            self._db.query(FaceDetection)
            .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
            .first()
        )
        if face is None:
            raise HTTPException(status_code=404, detail="Face not found in project")
        return face

    def _get_assignment(
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

    def _activate_assignment(
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

    def _reject_assignment(
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

    def _delete_assignment(self, assignment: PersonFaceAssignment) -> None:
        self._db.delete(assignment)

    def _upsert_negative_constraint(
        self,
        *,
        project_id: int,
        face_id: int,
        not_person_id: int,
        source: str,
    ) -> None:
        row = (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id == face_id,
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .first()
        )
        if row is None:
            self._db.add(
                FaceNegativeConstraint(
                    project_id=project_id,
                    face_detection_id=face_id,
                    not_person_id=not_person_id,
                    source=source,
                )
            )
        else:
            row.source = source

    def _remove_negative_constraint(
        self,
        *,
        project_id: int,
        face_id: int,
        not_person_id: int,
    ) -> None:
        (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id == face_id,
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .delete(synchronize_session=False)
        )

    def _upsert_negative_constraints(
        self,
        *,
        project_id: int,
        pairs: Collection[tuple[int, int]],
        source: str,
    ) -> None:
        unique_pairs = sorted({(int(face_id), int(person_id)) for face_id, person_id in pairs})
        if not unique_pairs:
            return

        face_ids = sorted({face_id for face_id, _ in unique_pairs})
        person_ids = sorted({person_id for _, person_id in unique_pairs})
        existing_rows = (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id.in_(face_ids),
                FaceNegativeConstraint.not_person_id.in_(person_ids),
            )
            .all()
        )
        existing_by_pair = {
            (row.face_detection_id, row.not_person_id): row
            for row in existing_rows
        }

        for face_id, person_id in unique_pairs:
            row = existing_by_pair.get((face_id, person_id))
            if row is None:
                self._db.add(
                    FaceNegativeConstraint(
                        project_id=project_id,
                        face_detection_id=face_id,
                        not_person_id=person_id,
                        source=source,
                    )
                )
            else:
                row.source = source

    def _remove_negative_constraints_for_person(
        self,
        *,
        project_id: int,
        face_ids: Collection[int],
        not_person_id: int,
    ) -> None:
        unique_face_ids = sorted({int(face_id) for face_id in face_ids})
        if not unique_face_ids:
            return
        (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id.in_(unique_face_ids),
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .delete(synchronize_session=False)
        )

    def _refresh_person_counters(self, *, project_id: int, person_id: int) -> None:
        person = self._get_person_or_404(project_id, person_id)
        stats = (
            self._db.query(
                sa.func.count(PersonFaceAssignment.id),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.is_positive_sample.is_(True), 1), else_=0)
                ),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.assignment_status == STATUS_AUTO_ASSIGNED, 1), else_=0)
                ),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING, 1), else_=0)
                ),
            )
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .one()
        )
        person.sample_count = int(stats[0] or 0)
        person.confirmed_sample_count = int(stats[1] or 0)
        person.auto_assigned_count = int(stats[2] or 0)
        person.review_pending_count = int(stats[3] or 0)
        person.updated_at = datetime.now(timezone.utc)

    def _finalize_people_updates(
        self,
        *,
        project_id: int,
        person_ids: Collection[int],
    ) -> None:
        self._db.flush()
        for person_id in sorted({int(person_id) for person_id in person_ids}):
            self._refresh_person_counters(project_id=project_id, person_id=person_id)
            rebuild_person_centroid_prototype(
                self._db,
                project_id=project_id,
                person_id=person_id,
            )
