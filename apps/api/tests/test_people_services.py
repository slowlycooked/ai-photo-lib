from __future__ import annotations

import unittest

from sqlalchemy.exc import OperationalError

from app.services.people_audit_service import PeopleAuditService
from app.services.people_batch_review_service import (
    PeopleBatchRetryExhausted,
    PeopleBatchReviewService,
)


class _RollbackOnlyDb:
    def __init__(self) -> None:
        self.rollback_count = 0

    def rollback(self) -> None:
        self.rollback_count += 1


class PeopleAuditServiceTest(unittest.TestCase):
    def test_body_values_override_headers_and_context(self) -> None:
        audit = PeopleAuditService.resolve_batch_fields(
            headers={"x-request-id": "header-req", "x-operator": "header-op"},
            context_request_id="context-req",
            body_request_id=" body-req ",
            body_operator=" body-op ",
            header_operator="fastapi-header-op",
        )

        self.assertEqual(audit.request_id, "body-req")
        self.assertEqual(audit.operator, "body-op")

    def test_falls_back_to_context_request_id_and_unknown_operator(self) -> None:
        audit = PeopleAuditService.resolve_batch_fields(
            headers={},
            context_request_id="context-req",
            body_request_id=None,
            body_operator=None,
            header_operator=None,
        )

        self.assertEqual(audit.request_id, "context-req")
        self.assertEqual(audit.operator, "unknown")

    def test_trims_empty_and_truncates_audit_fields(self) -> None:
        audit = PeopleAuditService.resolve_batch_fields(
            headers={"x-request-id": "   ", "x-operator": "x" * 200},
            context_request_id=None,
            body_request_id=None,
            body_operator=None,
            header_operator=None,
        )

        self.assertIsNone(audit.request_id)
        self.assertEqual(audit.operator, "x" * 128)


class PeopleBatchReviewServiceRetryTest(unittest.TestCase):
    def test_execute_batch_with_retry_rolls_back_and_returns_attempt_count(self) -> None:
        db = _RollbackOnlyDb()
        service = PeopleBatchReviewService(db)  # type: ignore[arg-type]
        calls = 0

        def operation() -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OperationalError("SELECT 1", {}, Exception("temporary lock"))
            return "ok"

        result, attempts = service.execute_batch_with_retry(
            operation_name="people.batch_test",
            request_id="req-1",
            operator="tester",
            max_attempts=2,
            fn=operation,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(attempts, 2)
        self.assertEqual(db.rollback_count, 1)

    def test_execute_batch_with_retry_raises_after_exhaustion(self) -> None:
        db = _RollbackOnlyDb()
        service = PeopleBatchReviewService(db)  # type: ignore[arg-type]

        def operation() -> str:
            raise OperationalError("SELECT 1", {}, Exception("still locked"))

        with self.assertRaises(PeopleBatchRetryExhausted) as caught:
            service.execute_batch_with_retry(
                operation_name="people.batch_test",
                request_id="req-2",
                operator="tester",
                max_attempts=3,
                fn=operation,
            )

        self.assertEqual(caught.exception.attempts, 3)
        self.assertEqual(db.rollback_count, 3)


if __name__ == "__main__":
    unittest.main()
