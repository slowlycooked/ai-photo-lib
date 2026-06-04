from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional, TypeVar

from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from ..models.face import Person
from ..schemas.face import (
    PersonBatchActionResponse,
    PersonBatchMoveResponse,
    PersonFeedbackEffectsResponse,
    PersonSummaryResponse,
)
from .people_audit_service import PeopleAuditFields
from .people_feedback_effects_service import PeopleFeedbackEffects, PeopleFeedbackEffectsService
from .person_assignment_workflow_service import PersonAssignmentWorkflowService

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


class PeopleBatchReviewService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._feedback_effects = PeopleFeedbackEffectsService(db)
        self._workflow = PersonAssignmentWorkflowService(db, self._feedback_effects)

    def get_feedback_effects(self) -> PeopleFeedbackEffects:
        return self._feedback_effects.get()

    def confirm_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        return self._workflow.batch_confirm_review_pending(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
        )

    def reject_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, int]:
        return self._workflow.batch_reject_review_pending(
            project_id=project_id,
            person_id=person_id,
            face_detection_ids=face_detection_ids,
        )

    def move_review_pending(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
        face_detection_ids: list[int],
    ) -> tuple[Person, Person, int]:
        return self._workflow.batch_move_review_pending(
            project_id=project_id,
            source_person_id=source_person_id,
            target_person_id=target_person_id,
            face_detection_ids=face_detection_ids,
        )

    def batch_confirm_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        audit: PeopleAuditFields,
        max_attempts: int,
    ) -> PersonBatchActionResponse:
        def _op() -> PersonBatchActionResponse:
            person, updated = self.confirm_review_pending(
                project_id=project_id,
                person_id=person_id,
                face_detection_ids=face_detection_ids,
            )
            logger.info(
                "people.batch_confirm_review project_id=%d person_id=%d updated=%d request_id=%s operator=%s",
                project_id,
                person_id,
                updated,
                audit.request_id,
                audit.operator,
            )
            return PersonBatchActionResponse(
                updated=updated,
                person=PersonSummaryResponse.model_validate(person),
                feedback_effects=PersonFeedbackEffectsResponse.model_validate(self.get_feedback_effects()),
            )

        return self._execute_response_with_retry(
            operation_name="people.batch_confirm_review",
            audit=audit,
            max_attempts=max_attempts,
            fn=_op,
        )

    def batch_reject_review_pending(
        self,
        *,
        project_id: int,
        person_id: int,
        face_detection_ids: list[int],
        audit: PeopleAuditFields,
        max_attempts: int,
    ) -> PersonBatchActionResponse:
        def _op() -> PersonBatchActionResponse:
            person, updated = self.reject_review_pending(
                project_id=project_id,
                person_id=person_id,
                face_detection_ids=face_detection_ids,
            )
            logger.info(
                "people.batch_reject_review project_id=%d person_id=%d updated=%d request_id=%s operator=%s",
                project_id,
                person_id,
                updated,
                audit.request_id,
                audit.operator,
            )
            return PersonBatchActionResponse(
                updated=updated,
                person=PersonSummaryResponse.model_validate(person),
                feedback_effects=PersonFeedbackEffectsResponse.model_validate(self.get_feedback_effects()),
            )

        return self._execute_response_with_retry(
            operation_name="people.batch_reject_review",
            audit=audit,
            max_attempts=max_attempts,
            fn=_op,
        )

    def batch_move_review_pending(
        self,
        *,
        project_id: int,
        source_person_id: int,
        target_person_id: int,
        face_detection_ids: list[int],
        audit: PeopleAuditFields,
        max_attempts: int,
    ) -> PersonBatchMoveResponse:
        def _op() -> PersonBatchMoveResponse:
            source_person, target_person, updated = self.move_review_pending(
                project_id=project_id,
                source_person_id=source_person_id,
                target_person_id=target_person_id,
                face_detection_ids=face_detection_ids,
            )
            logger.info(
                "people.batch_move_review project_id=%d source_person_id=%d target_person_id=%d updated=%d request_id=%s operator=%s",
                project_id,
                source_person.id,
                target_person.id,
                updated,
                audit.request_id,
                audit.operator,
            )
            return PersonBatchMoveResponse(
                updated=updated,
                source_person=PersonSummaryResponse.model_validate(source_person),
                target_person=PersonSummaryResponse.model_validate(target_person),
                feedback_effects=PersonFeedbackEffectsResponse.model_validate(self.get_feedback_effects()),
            )

        return self._execute_response_with_retry(
            operation_name="people.batch_move_review",
            audit=audit,
            max_attempts=max_attempts,
            fn=_op,
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

    def _execute_response_with_retry(
        self,
        *,
        operation_name: str,
        audit: PeopleAuditFields,
        max_attempts: int,
        fn: Callable[[], T],
    ) -> T:
        try:
            payload, attempts = self.execute_batch_with_retry(
                operation_name=operation_name,
                request_id=audit.request_id,
                operator=audit.operator,
                max_attempts=max_attempts,
                fn=fn,
            )
        except PeopleBatchRetryExhausted as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        payload.request_id = audit.request_id
        payload.operator = audit.operator
        payload.attempts = attempts
        return payload
