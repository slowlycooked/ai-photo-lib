from __future__ import annotations

from collections.abc import Callable
from typing import Optional, TypeVar

from sqlalchemy.orm import Session

from ..models.face import Person
from .people_assignment_mutation_service import PeopleAssignmentMutationService
from .people_batch_review_service import PeopleBatchRetryExhausted, PeopleBatchReviewService
from .people_feedback_effects_service import PeopleFeedbackEffects
from .people_lifecycle_mutation_service import PeopleLifecycleMutationService

T = TypeVar("T")


class PeopleMutationService:
    """Compatibility facade for older callers; prefer the focused People services."""

    def __init__(self, db: Session) -> None:
        self._assignment = PeopleAssignmentMutationService(db)
        self._batch_review = PeopleBatchReviewService(db)
        self._lifecycle = PeopleLifecycleMutationService(db)

    def get_feedback_effects(self) -> PeopleFeedbackEffects:
        lifecycle_effects = self._lifecycle.get_feedback_effects()
        assignment_effects = self._assignment.get_feedback_effects()
        batch_effects = self._batch_review.get_feedback_effects()
        if lifecycle_effects.project_id is not None:
            return lifecycle_effects
        if assignment_effects.project_id is not None:
            return assignment_effects
        return batch_effects

    def create_person(
        self,
        *,
        project_id: int,
        display_name: Optional[str],
        is_named: bool,
    ) -> Person:
        return self._lifecycle.create_person(
            project_id=project_id,
            display_name=display_name,
            is_named=is_named,
        )

    def rename_person(
        self,
        *,
        project_id: int,
        person_id: int,
        display_name: str,
    ) -> Person:
        return self._lifecycle.rename_person(
            project_id=project_id,
            person_id=person_id,
            display_name=display_name,
        )

    def delete_person(
        self,
        *,
        project_id: int,
        person_id: int,
    ) -> None:
        self._lifecycle.delete_person(project_id=project_id, person_id=person_id)

    def merge_people(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person, int]:
        return self._lifecycle.merge_people(
            project_id=project_id,
            source_person_id=source_person_id,
            target_person_id=target_person_id,
        )

    def split_person(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        new_display_name: Optional[str],
    ) -> tuple[Person, Person, int]:
        return self._lifecycle.split_person(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
            new_display_name=new_display_name,
        )

    def confirm_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self._assignment.confirm_assignment(
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
        return self._assignment.exclude_assignment(
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
        return self._assignment.move_face(
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
        return self._assignment.set_cover_face(
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

    def batch_confirm_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        return self._batch_review.confirm_review_pending(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
        )

    def batch_reject_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        return self._batch_review.reject_review_pending(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
        )

    def batch_move_review_pending(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, Person, int]:
        return self._batch_review.move_review_pending(
            project_id=project_id,
            source_person_id=source_person_id,
            target_person_id=target_person_id,
            face_detection_ids=face_detection_ids,
        )

    def execute_batch_with_retry(
        self,
        *,
        operation_name: str,
        request_id: Optional[str],
        operator: str,
        max_attempts: int,
        fn: Callable[[], T],
    ) -> tuple[T, int]:
        return self._batch_review.execute_batch_with_retry(
            operation_name=operation_name,
            request_id=request_id,
            operator=operator,
            max_attempts=max_attempts,
            fn=fn,
        )
