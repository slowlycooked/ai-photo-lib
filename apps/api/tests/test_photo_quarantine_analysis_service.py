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


def _decision(category: str, decision: str = "QUARANTINE") -> str:
    return json.dumps(
        {
            "decision": decision,
            "classification": category,
            "confidence": 0.99,
            "reason": "test",
            "preservation_flags": [],
            "has_record_value": False,
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


def test_hour_window_supports_normal_and_overnight_ranges() -> None:
    assert is_hour_in_window(1, 1, 6)
    assert not is_hour_in_window(6, 1, 6)
    assert is_hour_in_window(23, 22, 3)
    assert is_hour_in_window(2, 22, 3)
    assert not is_hour_in_window(12, 22, 3)
