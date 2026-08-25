from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
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
def quarantine_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "thumbnail_path", str(tmp_path / "thumbs"))
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


def _mark_legacy_quarantined(
    db: Session, *, trash: Path, original: Path
) -> tuple[PhotoQuarantineItem, Path]:
    item = db.query(PhotoQuarantineItem).filter(PhotoQuarantineItem.id == 100).one()
    photo = db.query(Photo).filter(Photo.id == 10).one()
    moved_path = trash / "legacy" / original.name
    moved_path.parent.mkdir(parents=True)
    original.replace(moved_path)
    now = datetime.now(timezone.utc)
    item.status = "quarantined"
    item.quarantine_path = str(moved_path)
    item.moved_at = now
    photo.status = "quarantined"
    photo.deleted_at = now
    db.commit()
    return item, moved_path


def test_move_queues_original_for_nas_worker(quarantine_fixture) -> None:
    engine, _library, trash, original, digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        result = service.move(project_id=1, item_id=100)
        assert result.moved is False
        assert result.item.status == "delete_queued"
        assert result.item.quarantine_path is None
        assert original.read_bytes() == b"test-photo-content"
        assert result.item.content_hash == digest

        repeated = service.move(project_id=1, item_id=100)
        assert repeated.moved is False

        manifest = original.parents[2] / "pending-original-trash.jsonl"
        entries = [json.loads(line) for line in manifest.read_text().splitlines()]
        assert len(entries) == 1
        assert entries[0]["action"] == "move_original_to_trash"
        assert entries[0]["photo_id"] == 10
        assert entries[0]["relative_path"] == "album/IMG_0001.jpg"

        photo = db.query(Photo).filter(Photo.id == 10).one()
        assert photo.status == "quarantined"
        assert photo.deleted_at is not None

        with pytest.raises(PhotoQuarantineConflict, match="cannot be restored"):
            service.restore(project_id=1, item_id=100)


def test_delete_approval_also_records_trash_label(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        item = db.query(PhotoQuarantineItem).filter(PhotoQuarantineItem.id == 100).one()
        item.status = "analysis_failed"
        db.commit()

        result = PhotoQuarantineService(db, root=trash).request_delete(
            project_id=1,
            item_id=100,
            labeled_by="martin",
        )

        assert result.item.status == "delete_queued"
        assert result.item.decision == "QUARANTINE"
        assert result.item.human_label == "TRASH"
        assert result.item.human_labeled_by == "martin"
        assert original.exists()


def test_batch_request_delete_uses_approval_semantics(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        result = PhotoQuarantineService(db, root=trash).batch_action(
            project_id=1,
            item_ids=[100],
            action="REQUEST_DELETE",
            labeled_by="martin",
        )

        assert result.succeeded == 1
        assert result.results[0].item is not None
        assert result.results[0].item.human_label == "TRASH"
        assert original.exists()

        manifest = original.parents[2] / "pending-original-trash.jsonl"
        entries = [json.loads(line) for line in manifest.read_text().splitlines()]
        assert [entry["photo_id"] for entry in entries] == [10]


def test_repeated_delete_request_recreates_missing_manifest(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    manifest = original.parents[2] / "pending-original-trash.jsonl"

    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        service.request_delete(project_id=1, item_id=100, labeled_by="martin")
        manifest.unlink()

        repeated = service.request_delete(
            project_id=1,
            item_id=100,
            labeled_by="martin",
        )

        assert repeated.item.status == "delete_queued"
        entries = [json.loads(line) for line in manifest.read_text().splitlines()]
        assert [entry["photo_id"] for entry in entries] == [10]


def test_restore_never_overwrites_occupied_original_path(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        item, moved_path = _mark_legacy_quarantined(
            db, trash=trash, original=original
        )
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b"new-file-at-original-path")

        with pytest.raises(PhotoQuarantineConflict, match="no file was overwritten"):
            service.restore(project_id=1, item_id=100)

        assert original.read_bytes() == b"new-file-at-original-path"
        assert moved_path.read_bytes() == b"test-photo-content"
        db.refresh(item)
        assert item.status == "restore_conflict"


def test_confirm_deleted_waits_for_nas_worker(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        service.move(project_id=1, item_id=100)

        with pytest.raises(PhotoQuarantineConflict, match="never deletes files"):
            service.confirm_deleted(project_id=1, item_id=100)
        assert original.exists()

        original.unlink()
        confirmed = service.confirm_deleted(project_id=1, item_id=100)
        assert confirmed.status == "deleted_confirmed"
        assert confirmed.deleted_confirmed_at is not None


def test_keep_records_human_decision_without_moving_file(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        kept = service.keep(project_id=1, item_id=100, labeled_by="martin")

        assert kept.status == "kept"
        assert kept.decision == "KEEP"
        assert kept.human_label == "KEEP"
        assert kept.human_labeled_by == "martin"
        assert kept.human_labeled_at is not None
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


def test_calibration_report_flags_model_false_positive(quarantine_fixture) -> None:
    engine, _library, trash, _original, _digest = quarantine_fixture
    candidate = {
        "decision": "QUARANTINE",
        "classification": "accidental_capture",
        "confidence": 0.99,
        "preservation_flags": [],
        "has_record_value": False,
    }
    with Session(engine) as db:
        item = db.query(PhotoQuarantineItem).filter(PhotoQuarantineItem.id == 100).one()
        item.first_result = candidate
        item.verification_result = candidate.copy()
        db.commit()

        service = PhotoQuarantineService(db, root=trash)
        service.label(
            project_id=1,
            item_id=100,
            label="KEEP",
            labeled_by="martin",
            note="这是需要保留的施工记录",
        )
        report = service.calibration_report(project_id=1)

        assert report["labeled_total"] == 1
        assert report["human_keep"] == 1
        assert report["false_positive"] == 1
        assert report["precision"] == 0.0
        assert report["false_positive_rate"] == 1.0
        assert report["zero_false_positive_met"] is False
        assert report["ready_for_auto_move"] is False
        assert report["categories"] == [{
            "classification": "accidental_capture",
            "labeled_total": 1,
            "human_keep": 1,
            "human_trash": 0,
            "true_positive": 0,
            "false_positive": 1,
            "true_negative": 0,
            "false_negative": 0,
        }]


def test_restore_records_put_back_as_keep_feedback(quarantine_fixture) -> None:
    engine, _library, trash, original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        _mark_legacy_quarantined(db, trash=trash, original=original)
        restored = service.restore(project_id=1, item_id=100, labeled_by="martin")

        assert restored.human_label == "KEEP"
        assert restored.human_labeled_by == "martin"


def test_list_items_can_select_unlabeled_calibration_sample(quarantine_fixture) -> None:
    engine, _library, trash, _original, _digest = quarantine_fixture
    with Session(engine) as db:
        service = PhotoQuarantineService(db, root=trash)
        total, items = service.list_items(project_id=1, human_label="UNLABELED")
        assert total == 1
        assert [item.id for item in items] == [100]

        service.label(
            project_id=1,
            item_id=100,
            label="KEEP",
            labeled_by="martin",
        )
        total, items = service.list_items(project_id=1, human_label="UNLABELED")
        assert total == 0
        assert items == []
