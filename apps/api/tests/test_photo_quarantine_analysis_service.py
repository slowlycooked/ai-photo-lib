from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.photo import Photo
from app.models.folder import ProjectFolder
from app.models.photo_quarantine import (
    PhotoQuarantineItem,
    ProjectPhotoQuarantineSettings,
)
from app.models.project import Project
from app.schemas.photo_quarantine import PhotoQuarantineItemResponse
from app.services.photo_quarantine_analysis_service import (
    PhotoQuarantineAnalysisService,
    is_hour_in_window,
)


def _build_db(tmp_path: Path, *, dry_run: bool = True) -> tuple[Session, Path]:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE project_folders (id INTEGER PRIMARY KEY)")
    Base.metadata.create_all(
        engine,
        tables=[
            Project.__table__,
            Photo.__table__,
            ProjectPhotoQuarantineSettings.__table__,
            PhotoQuarantineItem.__table__,
        ],
    )
    image = tmp_path / "library" / "photo.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"photo")
    db = Session(engine)
    db.add(Project(id=1, name="p", photo_library_path=str(image.parent), is_default=True))
    db.add(Photo(id=1, project_id=1, file_path=str(image), file_name=image.name, status="indexed"))
    db.add(
        ProjectPhotoQuarantineSettings(
            id=1,
            project_id=1,
            enabled=True,
            dry_run=dry_run,
            start_hour=1,
            end_hour=6,
            timezone="Asia/Shanghai",
            model_name="qwen3.8:27b",
            retention_days=30,
        )
    )
    db.commit()
    return db, image


def _decision(
    category: str,
    decision: str = "QUARANTINE",
    *,
    content_rating: str = "SAFE",
    sensitive_content_flags: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "decision": decision,
            "classification": category,
            "confidence": 0.99,
            "reason": "test",
            "preservation_flags": [],
            "has_record_value": False,
            "content_rating": content_rating,
            "sensitive_content_flags": sensitive_content_flags or [],
        }
    )


def test_two_matching_passes_create_dry_run_review(tmp_path: Path) -> None:
    db, _image = _build_db(tmp_path)
    outputs = iter([_decision("accidental_capture"), _decision("accidental_capture")])
    service = PhotoQuarantineAnalysisService(
        db,
        analyzer=lambda *_args, **_kwargs: next(outputs),
        clock=lambda tz: datetime(2026, 8, 25, 2, tzinfo=tz),
    )
    result = service.run_project(project_id=1)
    item = db.query(PhotoQuarantineItem).one()
    assert result["analyzed"] == 1
    assert item.decision == "QUARANTINE"
    assert item.status == "review"
    assert item.verification_result is not None


def test_screenshot_is_never_auto_move_category(tmp_path: Path) -> None:
    db, _image = _build_db(tmp_path)
    calls = []

    def analyzer(*_args, **_kwargs):
        calls.append(1)
        return _decision("screenshot")

    service = PhotoQuarantineAnalysisService(
        db,
        analyzer=analyzer,
        clock=lambda tz: datetime(2026, 8, 25, 2, tzinfo=tz),
    )
    service.run_project(project_id=1)
    item = db.query(PhotoQuarantineItem).one()
    assert len(calls) == 1
    assert item.decision == "QUARANTINE"
    assert item.status == "review"
    assert item.verification_result is None


def test_adult_content_is_flagged_and_forced_to_manual_review(tmp_path: Path) -> None:
    db, _image = _build_db(tmp_path, dry_run=False)
    service = PhotoQuarantineAnalysisService(
        db,
        analyzer=lambda *_args, **_kwargs: _decision(
            "other",
            decision="QUARANTINE",
            content_rating="SENSITIVE",
            sensitive_content_flags=["nudity", "violence"],
        ),
        clock=lambda tz: datetime(2026, 8, 25, 2, tzinfo=tz),
    )

    result = service.run_project(project_id=1)
    item = db.query(PhotoQuarantineItem).one()

    assert result["review"] == 1
    assert item.decision == "REVIEW"
    assert item.status == "review"
    assert item.content_rating == "ADULT"
    assert item.sensitive_content_flags == ["nudity", "violence"]
    assert item.quarantine_path is None
    assert "18+" in item.reason
    response = PhotoQuarantineItemResponse.model_validate(item)
    assert response.content_rating == "ADULT"
    assert response.sensitive_content_flags == ["nudity", "violence"]


def test_sensitive_content_payload_rejects_unknown_flags(tmp_path: Path) -> None:
    db, _image = _build_db(tmp_path)
    service = PhotoQuarantineAnalysisService(
        db,
        analyzer=lambda *_args, **_kwargs: _decision(
            "other",
            decision="REVIEW",
            content_rating="SENSITIVE",
            sensitive_content_flags=["unknown_risk"],
        ),
        clock=lambda tz: datetime(2026, 8, 25, 2, tzinfo=tz),
    )

    result = service.run_project(project_id=1)
    item = db.query(PhotoQuarantineItem).one()

    assert result["errors"] == 1
    assert item.status == "analysis_failed"
    assert item.decision == "REVIEW"


def test_exact_hash_duplicate_marks_only_newer_copy_for_review(tmp_path: Path) -> None:
    db, image = _build_db(tmp_path)
    duplicate = image.with_name("photo-copy.jpg")
    duplicate.write_bytes(image.read_bytes())
    db.query(Photo).filter(Photo.id == 1).update({"file_hash": "same-hash"})
    db.add(
        Photo(
            id=2,
            project_id=1,
            file_path=str(duplicate),
            file_name=duplicate.name,
            file_hash="same-hash",
            status="indexed",
        )
    )
    db.commit()
    analyzer_calls = []

    def analyzer(*_args, **_kwargs):
        analyzer_calls.append(1)
        return _decision("valuable", decision="KEEP")

    service = PhotoQuarantineAnalysisService(
        db,
        analyzer=analyzer,
        clock=lambda tz: datetime(2026, 8, 25, 2, tzinfo=tz),
    )

    result = service.run_project(project_id=1)
    items = db.query(PhotoQuarantineItem).order_by(PhotoQuarantineItem.photo_id).all()

    assert result["analyzed"] == 2
    assert len(analyzer_calls) == 1
    assert items[0].classification == "valuable"
    assert items[0].status == "kept"
    assert items[1].classification == "suspected_duplicate"
    assert items[1].status == "review"
    assert items[1].first_result["duplicate_photo_id"] == 1
    assert items[1].first_result["duplicate_original_path"] == str(image)


def test_hour_window_supports_normal_and_overnight_ranges() -> None:
    assert is_hour_in_window(1, 1, 6)
    assert not is_hour_in_window(6, 1, 6)
    assert is_hour_in_window(23, 22, 3)
    assert is_hour_in_window(2, 22, 3)
    assert not is_hour_in_window(12, 22, 3)
