from __future__ import annotations

import os
from datetime import date, datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.search.metadata_recall import _coerce_datetime_boundary  # noqa: E402


def test_coerce_datetime_boundary_accepts_iso_date_string() -> None:
    result = _coerce_datetime_boundary("2025-01-01")

    assert result == datetime(2025, 1, 1, 0, 0, 0)


def test_coerce_datetime_boundary_accepts_iso_datetime_string() -> None:
    result = _coerce_datetime_boundary("2025-01-01T12:34:56")

    assert result == datetime(2025, 1, 1, 12, 34, 56)


def test_coerce_datetime_boundary_accepts_date_and_datetime_instances() -> None:
    from_date = _coerce_datetime_boundary(date(2025, 1, 2))
    from_datetime = _coerce_datetime_boundary(datetime(2025, 1, 2, 3, 4, 5))

    assert from_date == datetime(2025, 1, 2, 0, 0, 0)
    assert from_datetime == datetime(2025, 1, 2, 3, 4, 5)


def test_coerce_datetime_boundary_returns_none_for_invalid_input() -> None:
    assert _coerce_datetime_boundary("not-a-date") is None
    assert _coerce_datetime_boundary(123) is None
