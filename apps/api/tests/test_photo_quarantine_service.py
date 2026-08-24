from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.photo import Photo
from app.models.folder import ProjectFolder
from app.models.photo_quarantine import PhotoQuarantineItem
from app.models.project import Project
from app.services.photo_quarantine_service import (
    PhotoQuarantineConflict,
    PhotoQuarantineService,
)


@pytest.fixture()
def quarantine_fixture(tmp_path: Path):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE project_folders (id INTEGER PRIMARY KEY)")
    Base.metadata.create_all(
        engine,
        tables=[
            Project.__table__,
            Photo.__table__,
            PhotoQuarantineItem.__table__,
        ],
    )
    library = tmp_path / "library"
    trash = tmp_path / "tobetrash"
    original = library / "album" / "IMG_0001.jpg"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"test-photo-content")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()

    with Session(engine) as db:
        db.add(
            Project(
                id=1,
                name="test",
                photo_library_path=str(library),
                thumbnail_path=str(tmp_path / "thumbs"),
                is_default=True,
            )
        )
        db.add(
            Photo(
                id=10,
                project_id=1,
                file_path=str(original),
                file_name=original.name,
                file_hash=digest,
                status="indexed",
            )
        )
        db.add(
            PhotoQuarantineItem(
                id=100,
                project_id=1,
                photo_id=10,
                status="review",
                decision="QUARANTINE",
                classification="accidental_capture",
                confidence=0.99,
                reason="no record value",
                preservation_flags=[],
                first_result={"decision": "QUARANTINE"},
                verification_result={"decision": "QUARANTINE"},
                model_name="qwen3.8:27b",
                prompt_version="photo-trash-v1",
                original_path=str(original),
                content_hash=digest,
            )
        )
        db.commit()

    return engine, library, trash, original, digest


def test_move_and_restore_preserve_photo_record(quarantine_fixture) -> None:
    engine, _library, trash, original, digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        result = service.move(project_id=1, item_id=100)
        moved_path = Path(result.item.quarantine_path or "")
        assert result.moved is True
        assert moved_path == trash / "project-1" / result.item.moved_at.date().isoformat() / "100" / original.name
        assert moved_path.read_bytes() == b"test-photo-content"
        assert not original.exists()
        assert result.item.content_hash == digest

        photo = db.query(Photo).filter(Photo.id == 10).one()
        assert photo.status == "quarantined"
        assert photo.deleted_at is not None

        restored = service.restore(project_id=1, item_id=100)
        assert restored.status == "restored"
        assert original.read_bytes() == b"test-photo-content"
        assert not moved_path.exists()
        db.refresh(photo)
        assert photo.status == "indexed"
        assert photo.deleted_at is None


def test_restore_never_overwrites_occupied_original_path(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        item = service.move(project_id=1, item_id=100).item
        moved_path = Path(item.quarantine_path or "")
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"new-file-at-original-path")

        with pytest.raises(PhotoQuarantineConflict, match="no file was overwritten"):
            service.restore(project_id=1, item_id=100)

        assert original.read_bytes() == b"new-file-at-original-path"
        assert moved_path.read_bytes() == b"test-photo-content"
        db.refresh(item)
        assert item.status == "restore_conflict"


def test_confirm_deleted_refuses_to_delete_existing_file(quarantine_fixture) -> None:
    engine, _library, trash, _original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        item = service.move(project_id=1, item_id=100).item
        path = Path(item.quarantine_path or "")

        with pytest.raises(PhotoQuarantineConflict, match="never deletes files"):
            service.confirm_deleted(project_id=1, item_id=100)
        assert path.exists()

        path.unlink()
        confirmed = service.confirm_deleted(project_id=1, item_id=100)
        assert confirmed.status == "deleted_confirmed"
        assert confirmed.deleted_confirmed_at is not None


def test_keep_records_human_decision_without_moving_file(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        kept = service.keep(project_id=1, item_id=100)

        assert kept.status == "kept"
        assert kept.decision == "KEEP"
        assert original.read_bytes() == b"test-photo-content"
        photo = db.query(Photo).filter(Photo.id == 10).one()
        assert photo.status == "indexed"
        assert photo.deleted_at is None


def test_batch_action_reports_partial_success_without_rolling_back(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        result = PhotoQuarantineService(db, root=trash).batch_action(
            project_id=1,
            item_ids=[100, 999],
            action="KEEP",
        )

        assert result.succeeded == 1
        assert result.failed == 1
        assert result.results[0].item is not None
        assert result.results[0].item.status == "kept"
        assert result.results[1].error_code == "invalid_item"
        assert original.exists()


def test_batch_action_cannot_mutate_another_project_item(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        result = PhotoQuarantineService(db, root=trash).batch_action(
            project_id=2,
            item_ids=[100],
            action="KEEP",
        )

        assert result.succeeded == 0
        assert result.failed == 1
        assert result.results[0].error_code == "invalid_item"
        item = db.query(PhotoQuarantineItem).filter(PhotoQuarantineItem.id == 100).one()
        assert item.status == "review"
        assert original.exists()


def test_batch_action_redacts_unexpected_io_failure(quarantine_fixture) -> None:
    engine, _library, trash, _original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)

        def fail_keep(**_kwargs):
            raise OSError("private NAS path details")

        service.keep = fail_keep  # type: ignore[method-assign]
        with patch("app.services.photo_quarantine_service.logger.exception") as log_exception:
            result = service.batch_action(project_id=1, item_ids=[100], action="KEEP")

        assert result.failed == 1
        assert result.results[0].error_code == "operation_failed"
        assert result.results[0].message == "Operation failed; check server logs"
        log_exception.assert_called_once_with(
            "photo_quarantine.batch_item_failed project_id=%d item_id=%d action=%s",
            1,
            100,
            "KEEP",
        )
