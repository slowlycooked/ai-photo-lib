from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..config import settings
from ..models.face import ProjectFaceSettings
from ..models.project import Project
from ..models.project_task import ProjectTask
from .project_task_service import (
    TASK_TYPE_FACE_REMATCH_UNKNOWN,
    enqueue_face_rematch_unknown_task,
)

_AUTO_REMATCH_TRIGGER = "scheduled_auto_rematch"


@dataclass(frozen=True)
class FaceAutoRematchScheduleResult:
    projects_checked: int = 0
    tasks_created: int = 0
    tasks_reused: int = 0
    skipped_recent: int = 0
    skipped_disabled: int = 0


class FaceAutoRematchScheduler:
    def __init__(self, db: Session) -> None:
        self._db = db

    def run_once(self, *, now: datetime | None = None) -> FaceAutoRematchScheduleResult:
        schedule = _normalize_schedule(settings.face_auto_rematch_schedule)
        if not settings.face_auto_rematch_enabled or schedule == "off":
            return FaceAutoRematchScheduleResult(skipped_disabled=1)

        current_time = now or datetime.now(timezone.utc)
        interval = _schedule_interval(schedule)
        max_faces = max(1, int(settings.face_auto_rematch_max_faces or 5000))

        projects = (
            self._db.query(Project.id)
            .join(ProjectFaceSettings, ProjectFaceSettings.project_id == Project.id)
            .filter(
                Project.deleted_at.is_(None),
                ProjectFaceSettings.face_recognition_enabled.is_(True),
            )
            .order_by(Project.id.asc())
            .all()
        )

        projects_checked = 0
        tasks_created = 0
        tasks_reused = 0
        skipped_recent = 0

        for row in projects:
            project_id = int(row[0])
            projects_checked += 1
            if self._has_recent_scheduled_rematch(
                project_id=project_id,
                since=current_time - interval,
            ):
                skipped_recent += 1
                continue

            result = enqueue_face_rematch_unknown_task(
                self._db,
                project_id=project_id,
                max_faces=max_faces,
                scope="unknown",
                trigger=_AUTO_REMATCH_TRIGGER,
                schedule=schedule,
            )
            if result.created:
                tasks_created += 1
            else:
                tasks_reused += 1

        return FaceAutoRematchScheduleResult(
            projects_checked=projects_checked,
            tasks_created=tasks_created,
            tasks_reused=tasks_reused,
            skipped_recent=skipped_recent,
        )

    def _has_recent_scheduled_rematch(self, *, project_id: int, since: datetime) -> bool:
        recent_tasks = (
            self._db.query(ProjectTask)
            .filter(
                ProjectTask.project_id == project_id,
                ProjectTask.task_type == TASK_TYPE_FACE_REMATCH_UNKNOWN,
            )
            .order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc())
            .limit(20)
            .all()
        )
        since_naive = _to_naive_utc(since)
        for task in recent_tasks:
            params = dict(task.request_params or {})
            if params.get("trigger") != _AUTO_REMATCH_TRIGGER:
                continue
            created_at = _to_naive_utc(task.created_at)
            if created_at >= since_naive:
                return True
        return False


def _normalize_schedule(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in {"off", "none", "disabled", "false", "0"}:
        return "off"
    if text in {"weekly", "week"}:
        return "weekly"
    return "daily"


def _schedule_interval(schedule: str) -> timedelta:
    if schedule == "weekly":
        return timedelta(days=7)
    return timedelta(days=1)


def _to_naive_utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
