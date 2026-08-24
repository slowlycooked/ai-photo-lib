from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.photo_quarantine import ProjectPhotoQuarantineSettings
from app.models.project import Project
from app.models.project_task import ProjectTask
from app.services.photo_quarantine_scheduler import PhotoQuarantineScheduler
from app.services.project_task_service import TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Project.__table__,
            ProjectPhotoQuarantineSettings.__table__,
            ProjectTask.__table__,
        ],
    )
    db = Session(engine)
    db.add(Project(id=1, name="p", photo_library_path="/tmp", is_default=True))
    db.add(
        ProjectPhotoQuarantineSettings(
            id=1,
            project_id=1,
            enabled=True,
            dry_run=True,
            start_hour=1,
            end_hour=6,
            timezone="Asia/Shanghai",
            model_name="qwen3.8:27b",
            retention_days=30,
        )
    )
    db.commit()
    return db


def test_scheduler_creates_only_one_task_per_local_day() -> None:
    db = _session()
    now = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)  # 02:00 Shanghai
    first = PhotoQuarantineScheduler(db).run_once(now=now)
    assert first.tasks_created == 1
    task = db.query(ProjectTask).one()
    task.status = "success"
    task.created_at = now.replace(tzinfo=None)
    db.commit()

    second = PhotoQuarantineScheduler(db).run_once(now=now)
    assert second.skipped_today == 1
    assert task.task_type == TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS
    assert task.request_params == {"trigger": "schedule", "ignore_window": False}


def test_scheduler_does_not_enqueue_outside_window() -> None:
    db = _session()
    now = datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc)  # 12:00 Shanghai
    result = PhotoQuarantineScheduler(db).run_once(now=now)
    assert result.skipped_outside_window == 1
    assert db.query(ProjectTask).count() == 0
