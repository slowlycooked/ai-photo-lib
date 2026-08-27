from __future__ import annotations

import os
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Required before importing app config at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.photo import Photo  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.project_photos_query_service import (  # noqa: E402
    PhotoCursorError,
    ProjectPhotosQueryService,
)


def _build_session():
    engine = sa.create_engine("sqlite:///:memory:", future=True)
    Project.__table__.create(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE project_folders (
                    id BIGINT PRIMARY KEY,
                    project_id BIGINT NOT NULL
                )
                """
            )
        )
    Photo.__table__.create(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_list_photos_uses_id_desc_as_stable_tie_breaker() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(
            Project(
                id=1,
                name="default",
                photo_library_path="/tmp/photos",
                thumbnail_path="/tmp/thumbs",
                is_default=True,
            )
        )

        same_taken_at = datetime(2026, 1, 1, 12, 0, 0)
        same_created_at = datetime(2026, 1, 2, 8, 30, 0)

        for photo_id in range(1, 7):
            db.add(
                Photo(
                    id=photo_id,
                    project_id=1,
                    file_path=f"/tmp/photos/{photo_id}.jpg",
                    file_name=f"{photo_id}.jpg",
                    taken_at=same_taken_at if photo_id > 2 else None,
                    created_at=same_created_at,
                    updated_at=same_created_at,
                )
            )

        db.commit()

        service = ProjectPhotosQueryService(db)
        _, page_1 = service.list_photos(
            project_id=1,
            page=1,
            page_size=3,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )
        _, page_2 = service.list_photos(
            project_id=1,
            page=2,
            page_size=3,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )

        page_1_ids = [photo.id for photo in page_1]
        page_2_ids = [photo.id for photo in page_2]

        assert page_1_ids == [6, 5, 4]
        assert page_2_ids == [3, 2, 1]
        assert set(page_1_ids).isdisjoint(page_2_ids)


def test_list_photos_clamps_page_before_building_offset() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(
            Project(
                id=1,
                name="default",
                photo_library_path="/tmp/photos",
                thumbnail_path="/tmp/thumbs",
                is_default=True,
            )
        )

        created_at = datetime(2026, 1, 2, 8, 30, 0)
        for photo_id in range(1, 4):
            db.add(
                Photo(
                    id=photo_id,
                    project_id=1,
                    file_path=f"/tmp/photos/{photo_id}.jpg",
                    file_name=f"{photo_id}.jpg",
                    taken_at=datetime(2026, 1, photo_id, 12, 0, 0),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

        db.commit()

        total, photos = ProjectPhotosQueryService(db).list_photos(
            project_id=1,
            page=0,
            page_size=2,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )

        assert total == 3
        assert [photo.id for photo in photos] == [3, 2]


def test_locate_photo_returns_direct_folder_page_and_position() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(Project(id=1, name="default", photo_library_path="/tmp/photos", is_default=True))
        created_at = datetime(2026, 1, 2, 8, 30, 0)
        photos = []
        for photo_id in range(1, 8):
            photo = Photo(
                id=photo_id,
                project_id=1,
                folder_id=10 if photo_id <= 6 else 20,
                folder_path="trip" if photo_id <= 6 else "other",
                file_path=f"/tmp/photos/{photo_id}.jpg",
                file_name=f"{photo_id}.jpg",
                taken_at=datetime(2026, 1, photo_id, 12, 0, 0),
                created_at=created_at,
                updated_at=created_at,
            )
            photos.append(photo)
            db.add(photo)
        db.commit()

        location = ProjectPhotosQueryService(db).locate_photo(photos[1], page_size=2)

        assert location.folder_id == 10
        assert location.folder_path == "trip"
        assert location.total == 6
        assert location.position == 5
        assert location.page == 3
        assert location.is_browsable is True


def test_locate_quarantined_photo_returns_nearest_original_folder_page() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(Project(id=1, name="default", photo_library_path="/tmp/photos", is_default=True))
        created_at = datetime(2026, 1, 2, 8, 30, 0)
        photos = []
        for photo_id in range(1, 7):
            photo = Photo(
                id=photo_id,
                project_id=1,
                folder_id=10,
                folder_path="trip",
                file_path=f"/tmp/photos/{photo_id}.jpg",
                file_name=f"{photo_id}.jpg",
                taken_at=datetime(2026, 1, photo_id, 12, 0, 0),
                status="quarantined" if photo_id == 2 else "pending",
                created_at=created_at,
                updated_at=created_at,
            )
            photos.append(photo)
            db.add(photo)
        db.commit()

        location = ProjectPhotosQueryService(db).locate_photo(photos[1], page_size=2)

        assert location.total == 5
        assert location.position == 5
        assert location.page == 3
        assert location.is_browsable is False


def test_cursor_pagination_returns_stable_non_overlapping_pages() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(
            Project(
                id=1,
                name="default",
                photo_library_path="/tmp/photos",
                thumbnail_path="/tmp/thumbs",
                is_default=True,
            )
        )
        same_taken_at = datetime(2026, 1, 1, 12, 0, 0)
        same_created_at = datetime(2026, 1, 2, 8, 30, 0)
        for photo_id in range(1, 7):
            db.add(
                Photo(
                    id=photo_id,
                    project_id=1,
                    file_path=f"/tmp/photos/{photo_id}.jpg",
                    file_name=f"{photo_id}.jpg",
                    taken_at=same_taken_at if photo_id > 2 else None,
                    created_at=same_created_at,
                    updated_at=same_created_at,
                )
            )
        db.commit()

        service = ProjectPhotosQueryService(db)
        statements: list[str] = []

        def record_statement(_conn, _cursor, statement, _params, _context, _executemany):
            statements.append(statement.lower())

        sa.event.listen(db.get_bind(), "before_cursor_execute", record_statement)
        first = service.list_photos_cursor(
            project_id=1,
            cursor=None,
            page_size=2,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )
        assert any("count(" in statement for statement in statements)
        statements.clear()
        second = service.list_photos_cursor(
            project_id=1,
            cursor=first.next_cursor,
            page_size=2,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )
        assert all("count(" not in statement for statement in statements)
        third = service.list_photos_cursor(
            project_id=1,
            cursor=second.next_cursor,
            page_size=2,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )

        assert [photo.id for photo in first.items] == [6, 5]
        assert [photo.id for photo in second.items] == [4, 3]
        assert [photo.id for photo in third.items] == [2, 1]
        assert [first.page, second.page, third.page] == [1, 2, 3]
        assert [first.total, second.total, third.total] == [6, 6, 6]
        assert first.has_more is True
        assert second.has_more is True
        assert third.has_more is False
        assert third.next_cursor is None


def test_cursor_pagination_rejects_filter_mismatch() -> None:
    SessionLocal = _build_session()

    with SessionLocal() as db:
        db.add(
            Project(
                id=1,
                name="default",
                photo_library_path="/tmp/photos",
                thumbnail_path="/tmp/thumbs",
                is_default=True,
            )
        )
        created_at = datetime(2026, 1, 2, 8, 30, 0)
        for photo_id in range(1, 4):
            db.add(
                Photo(
                    id=photo_id,
                    project_id=1,
                    file_path=f"/tmp/photos/{photo_id}.jpg",
                    file_name=f"{photo_id}.jpg",
                    taken_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        db.commit()

        service = ProjectPhotosQueryService(db)
        first = service.list_photos_cursor(
            project_id=1,
            cursor=None,
            page_size=2,
            date_from=None,
            date_to=None,
            folder_id=None,
            folder_scope="subtree",
        )

        try:
            service.list_photos_cursor(
                project_id=1,
                cursor=first.next_cursor,
                page_size=3,
                date_from=None,
                date_to=None,
                folder_id=None,
                folder_scope="subtree",
            )
        except PhotoCursorError as exc:
            assert "does not match" in str(exc)
        else:
            raise AssertionError("Expected a mismatched cursor to be rejected")
