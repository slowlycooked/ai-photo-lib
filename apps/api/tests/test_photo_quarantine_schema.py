from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.photo_quarantine import PhotoQuarantineBatchRequest


def test_batch_request_rejects_duplicate_item_ids() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        PhotoQuarantineBatchRequest(action="RESTORE", item_ids=[1, 1])


def test_batch_request_limits_batch_size() -> None:
    with pytest.raises(ValidationError):
        PhotoQuarantineBatchRequest(action="KEEP", item_ids=list(range(101)))


def test_batch_request_accepts_explicit_delete_approval() -> None:
    request = PhotoQuarantineBatchRequest(
        action="REQUEST_DELETE",
        item_ids=[1, 2],
    )

    assert request.action == "REQUEST_DELETE"


def test_batch_request_accepts_analysis_retry() -> None:
    request = PhotoQuarantineBatchRequest(
        action="RETRY_ANALYSIS",
        item_ids=[1, 2],
    )

    assert request.action == "RETRY_ANALYSIS"
