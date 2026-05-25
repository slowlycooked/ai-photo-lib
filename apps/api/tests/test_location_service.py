from __future__ import annotations

import os
from types import SimpleNamespace

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.location_cache import PhotoLocationCache  # noqa: E402
from app.services import location_service  # noqa: E402


class _FakeProvider(location_service.ReverseGeocodeProvider):
    name = "fake-provider"

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def resolve(
        self,
        latitude: float,
        longitude: float,
    ) -> location_service.ResolvedPhotoLocation:
        self.calls.append((latitude, longitude))
        return location_service.ResolvedPhotoLocation(
            country_code="CN",
            country_name="中国",
            admin1="浙江省",
            admin2="杭州市",
            city="杭州",
            district="西湖区",
            formatted_address="中国浙江省杭州市西湖区龙井路",
            location_source=self.name,
        )


def _build_photo(lat: float = 30.2741, lon: float = 120.1551) -> SimpleNamespace:
    return SimpleNamespace(
        gps_latitude=lat,
        gps_longitude=lon,
        country_code=None,
        country_name=None,
        admin1=None,
        admin2=None,
        city=None,
        district=None,
        formatted_address=None,
        location_source=None,
        location_resolved_at=None,
    )


def test_resolve_photo_location_uses_provider_then_cache(monkeypatch) -> None:
    engine = sa.create_engine("sqlite:///:memory:", future=True)
    PhotoLocationCache.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    fake = _FakeProvider()
    monkeypatch.setattr(location_service, "_build_provider", lambda: fake)

    with SessionLocal() as db:
        first = _build_photo()
        changed = location_service.resolve_photo_location(db, first)
        assert changed is True
        db.commit()
        assert first.city == "杭州"
        assert first.district == "西湖区"
        assert first.location_source == "fake-provider"
        assert len(fake.calls) == 1

        second = _build_photo()
        changed_second = location_service.resolve_photo_location(db, second)
        assert changed_second is True
        assert second.city == "杭州"
        assert len(fake.calls) == 1


def test_resolve_photo_location_no_provider_is_safe(monkeypatch) -> None:
    engine = sa.create_engine("sqlite:///:memory:", future=True)
    PhotoLocationCache.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(location_service, "_build_provider", lambda: None)

    with SessionLocal() as db:
        photo = _build_photo()
        changed = location_service.resolve_photo_location(db, photo)
        assert changed is False
        assert photo.city is None


def test_resolve_photo_location_same_session_duplicate_key_safe(monkeypatch) -> None:
    engine = sa.create_engine("sqlite:///:memory:", future=True)
    PhotoLocationCache.__table__.create(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    fake = _FakeProvider()
    monkeypatch.setattr(location_service, "_build_provider", lambda: fake)

    with SessionLocal() as db:
        first = _build_photo(40.9638, 115.3018)
        second = _build_photo(40.9638, 115.3018)

        assert location_service.resolve_photo_location(db, first) is True
        assert location_service.resolve_photo_location(db, second) is True

        db.commit()

        rows = db.query(PhotoLocationCache).all()
        assert len(rows) == 1
        assert rows[0].location_key == "40.9638,115.3018"
