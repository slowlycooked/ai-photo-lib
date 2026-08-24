from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.photo_quarantine import ProjectPhotoQuarantineSettings
from ..models.project import Project
from ..models.project_task import ProjectTask
from .photo_quarantine_analysis_service import is_hour_in_window, load_timezone
from .project_task_service import (
    TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS,
    enqueue_photo_quarantine_task,
)


@dataclass(frozen=True)
class PhotoQuarantineScheduleResult:
    projects_checked: int = 0
    tasks_created: int = 0
    tasks_reused: int = 0
    skipped_outside_window: int = 0
    skipped_today: int = 0


class PhotoQuarantineScheduler:
    def __init__(self, db: Session) -> None:
        self._db = db

    def run_once(self, *, now: datetime | None = None) -> PhotoQuarantineScheduleResult:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        rows = (
            self._db.query(ProjectPhotoQuarantineSettings)
            .join(Project, Project.id == ProjectPhotoQuarantineSettings.project_id)
            .filter(
                Project.deleted_at.is_(None),
                ProjectPhotoQuarantineSettings.enabled.is_(True),
            )
            .order_by(ProjectPhotoQuarantineSettings.project_id.asc())
            .all()
        )
        checked = created = reused = outside = today = 0
        for row in rows:
            checked += 1
            timezone_info = load_timezone(row.timezone)
            local_now = current.astimezone(timezone_info)
            if not is_hour_in_window(local_now.hour, row.start_hour, row.end_hour):
                outside += 1
                continue
            latest = (
                self._db.query(ProjectTask)
                .filter(
                    ProjectTask.project_id == row.project_id,
                    ProjectTask.task_type == TASK_TYPE_PHOTO_QUARANTINE_ANALYSIS,
                )
                .order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc())
                .first()
            )
            if latest is not None and _local_date(latest.created_at, timezone_info) == local_now.date():
                today += 1
                continue
            result = enqueue_photo_quarantine_task(
                self._db,
                project_id=row.project_id,
                trigger="schedule",
                ignore_window=False,
            )
            if result.created:
                created += 1
            else:
                reused += 1
        return PhotoQuarantineScheduleResult(
            projects_checked=checked,
            tasks_created=created,
            tasks_reused=reused,
            skipped_outside_window=outside,
            skipped_today=today,
        )


def _local_date(value: datetime, timezone_info):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone_info).date()
