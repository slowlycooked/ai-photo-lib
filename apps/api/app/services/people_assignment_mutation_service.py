from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.face import Person
from .people_feedback_effects_service import PeopleFeedbackEffects, PeopleFeedbackEffectsService
from .person_assignment_workflow_service import PersonAssignmentWorkflowService


class PeopleAssignmentMutationService:
    def __init__(self, db: Session) -> None:
        self._feedback_effects = PeopleFeedbackEffectsService(db)
        self._workflow = PersonAssignmentWorkflowService(db, self._feedback_effects)

    def get_feedback_effects(self) -> PeopleFeedbackEffects:
        return self._feedback_effects.get()

    def confirm_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self._workflow.confirm_assignment(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )

    def confirm_face_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self.confirm_assignment(project_id=project_id, person_id=person_id, face_id=face_id)

    def exclude_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self._workflow.exclude_assignment(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )

    def reject_face_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self.exclude_assignment(project_id=project_id, person_id=person_id, face_id=face_id)

    def move_face(
        self,
        *,
        project_id: int,
        source_person_id: int,
        face_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person]:
        return self._workflow.move_face(
            project_id=project_id,
            source_person_id=source_person_id,
            face_id=face_id,
            target_person_id=target_person_id,
        )

    def move_face_assignment(
        self,
        *,
        project_id: int,
        source_person_id: int,
        face_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person]:
        return self.move_face(
            project_id=project_id,
            source_person_id=source_person_id,
            face_id=face_id,
            target_person_id=target_person_id,
        )

    def set_cover_face(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self._workflow.set_cover_face(
            project_id=project_id,
            person_id=person_id,
            face_id=face_id,
        )

    def set_representative_face(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self.set_cover_face(project_id=project_id, person_id=person_id, face_id=face_id)
