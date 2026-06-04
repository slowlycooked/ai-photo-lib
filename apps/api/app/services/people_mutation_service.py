from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Collection, Optional, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from ..models.face import Person
from .people_feedback_effects_service import PeopleFeedbackEffects, PeopleFeedbackEffectsService
from .person_assignment_workflow_service import PersonAssignmentWorkflowService
from .person_lifecycle_mutation_service import PersonLifecycleMutationService

logger = logging.getLogger(__name__)

_BATCH_RETRYABLE_DB_ERRORS = (OperationalError, DBAPIError)
T = TypeVar("T")


class PeopleBatchRetryExhausted(RuntimeError):
    def __init__(self, operation_name: str, attempts: int, last_error: Optional[Exception]) -> None:
        self.operation_name = operation_name
        self.attempts = attempts
        self.last_error = last_error
        detail = f"{operation_name} failed after {attempts} attempts due to retryable database errors"
        if last_error is not None:
            detail = f"{detail}: {last_error}"
        super().__init__(detail)


class PeopleMutationService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._feedback_effects = PeopleFeedbackEffectsService(db)
        self._assignment_workflow = PersonAssignmentWorkflowService(db, self._feedback_effects)
        self._lifecycle = PersonLifecycleMutationService(db)

    def get_feedback_effects(self) -> PeopleFeedbackEffects:
        return self._feedback_effects.get()

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

    def create_person(
        self,
        *,
        project_id: int,
        display_name: Optional[str],
        is_named: bool,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lifecycle.create_person(
            project_id=project_id,
            display_name=display_name,
            is_named=is_named,
        )
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])
        return person

    def rename_person(
        self,
        *,
        project_id: int,
        person_id: int,
        display_name: str,
    ) -> Person:
        self._reset_feedback_effects()
        person = self._lifecycle.rename_person(
            project_id=project_id,
            person_id=person_id,
            display_name=display_name,
        )
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])
        return person

    def delete_person(
        self,
        *,
        project_id: int,
        person_id: int,
    ) -> None:
        self._reset_feedback_effects()
        self._lifecycle.delete_person(project_id=project_id, person_id=person_id)
        self._set_feedback_effects(project_id=project_id, rebuilt_person_ids=[])

    def merge_people(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
    ) -> tuple[Person, Person, int]:
        self._reset_feedback_effects()
        source_person, target_person, moved_assignments = self._lifecycle.merge_people(
            project_id=project_id,
            source_person_id=source_person_id,
            target_person_id=target_person_id,
        )
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        return source_person, target_person, moved_assignments

    def split_person(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        new_display_name: Optional[str],
    ) -> tuple[Person, Person, int]:
        self._reset_feedback_effects()
        source_person, target_person, moved_assignments = self._lifecycle.split_person(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
            new_display_name=new_display_name,
        )
        self._set_feedback_effects(
            project_id=project_id,
            rebuilt_person_ids=[source_person.id, target_person.id],
            rematch_scope="person",
            rematch_person_id=target_person.id,
        )
        return source_person, target_person, moved_assignments

    def confirm_assignment(
        self,
        *,
        project_id: int,
        person_id: int,
        face_id: int,
    ) -> Person:
        return self._assignment_workflow.confirm_assignment(
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
        return self._assignment_workflow.exclude_assignment(
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
        return self._assignment_workflow.move_face(
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
        return self._assignment_workflow.set_cover_face(
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
        return self._assignment_workflow.batch_confirm_review_pending(
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
        return self._assignment_workflow.batch_reject_review_pending(
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
        return self._assignment_workflow.batch_move_review_pending(
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
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return fn(), attempt
            except _BATCH_RETRYABLE_DB_ERRORS as exc:
                self._db.rollback()
                last_error = exc
                logger.warning(
                    "%s.retryable_db_error request_id=%s operator=%s attempt=%d/%d error=%s",
                    operation_name,
                    request_id,
                    operator,
                    attempt,
                    max_attempts,
                    exc,
                )

        raise PeopleBatchRetryExhausted(operation_name, max_attempts, last_error)
