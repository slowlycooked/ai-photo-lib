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
from app.services.project_photos_query_service import ProjectPhotosQueryService  # noqa: E402


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
                    taken_at=same_taken_at,
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
