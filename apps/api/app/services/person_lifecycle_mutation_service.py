from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import FaceNegativeConstraint, Person, PersonFaceAssignment
from .people_assignment_constants import STATUS_HUMAN_CORRECTED, STATUS_REJECTED
from .people_assignment_mutation_service import PeopleAssignmentMutationService
from .people_lookup_service import PeopleLookupService
from .people_negative_constraint_service import PeopleNegativeConstraintService
from .people_update_finalizer import PeopleUpdateFinalizer


class PersonLifecycleMutationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._assignments = PeopleAssignmentMutationService(db)
        self._finalizer = PeopleUpdateFinalizer(db)
        self._lookup = PeopleLookupService(db)
        self._negative_constraints = PeopleNegativeConstraintService(db)

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
        person = self._lookup.get_person_or_404(project_id, person_id)
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
        person = self._lookup.get_person_or_404(project_id, person_id)
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
        source_person = self._lookup.get_person_or_404(project_id, source_person_id)
        target_person = self._lookup.get_person_or_404(project_id, target_person_id)
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
            target_assignment = self._assignments.get(
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

            self._assignments.delete(assignment)

        if target_person.representative_face_detection_id is None:
            target_person.representative_face_detection_id = source_person.representative_face_detection_id
        source_person.representative_face_detection_id = None
        source_person.updated_at = now
        target_person.updated_at = now

        self._finalizer.finalize(project_id=project_id, person_ids=[source_person.id, target_person.id])
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
        source_person = self._lookup.get_person_or_404(project_id, person_id)
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
            self._assignments.delete(source_assignment)
            target_assignment = self._assignments.get(
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
                self._assignments.activate(
                    target_assignment,
                    status=STATUS_HUMAN_CORRECTED,
                    source="human_split",
                    now=now,
                    confidence=target_assignment.confidence,
                    similarity_score=target_assignment.similarity_score,
                )

            self._negative_constraints.upsert(
                project_id=project_id,
                face_id=face_detection_id,
                not_person_id=source_person.id,
                source="human_split",
            )
            self._negative_constraints.remove(
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

        self._finalizer.finalize(project_id=project_id, person_ids=[source_person.id, target_person.id])
        self._db.commit()
        self._db.refresh(source_person)
        self._db.refresh(target_person)
        return source_person, target_person, moved_assignments
