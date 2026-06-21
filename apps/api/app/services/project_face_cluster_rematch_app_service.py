from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..schemas.face import (
    FaceClusterUnknownResponse,
    FaceClusterUnknownStatusResponse,
    FaceRematchUnknownResponse,
    FaceRematchUnknownStatusResponse,
)
from .project_task_service import (
    FACE_CLUSTER_TASK_TYPES,
    FACE_REMATCH_TASK_TYPES,
    build_face_cluster_status,
    build_face_rematch_status,
    enqueue_face_cluster_task,
    enqueue_face_rematch_unknown_task,
    get_active_face_cluster_task,
    get_active_face_rematch_task,
    get_latest_face_cluster_task,
    get_latest_face_rematch_task,
    request_project_task_cancel,
)
from .project_face_settings_service import get_or_create_project_face_settings


class FaceRecognitionDisabledError(RuntimeError):
    pass


class FaceRematchValidationError(RuntimeError):
    pass


class FaceClusterTaskNotFoundError(RuntimeError):
    pass


class FaceRematchTaskNotFoundError(RuntimeError):
    pass


@dataclass
class ProjectFaceClusterRematchAppService:
    db: Session

    def enqueue_cluster(self, *, project_id: int, max_faces: int) -> FaceClusterUnknownResponse:
        settings = get_or_create_project_face_settings(self.db, project_id)
        if not settings.face_recognition_enabled:
            raise FaceRecognitionDisabledError(
                "Face recognition is disabled for this project. "
                "Enable it in face settings first."
            )
        result = enqueue_face_cluster_task(
            self.db,
            project_id=project_id,
            max_faces=max_faces,
        )
        return FaceClusterUnknownResponse(
            message=(
                "Unknown face clustering queued"
                if result.created
                else "Unknown face clustering already in progress"
            ),
            status=build_face_cluster_status(result.task),
        )

    def cluster_status(self, *, project_id: int) -> FaceClusterUnknownStatusResponse:
        active_task = get_active_face_cluster_task(self.db, project_id)
        if active_task is not None:
            return build_face_cluster_status(active_task)
        return build_face_cluster_status(get_latest_face_cluster_task(self.db, project_id))

    def cancel_cluster(self, *, project_id: int) -> FaceClusterUnknownStatusResponse:
        task = request_project_task_cancel(
            self.db,
            project_id=project_id,
            task_types=FACE_CLUSTER_TASK_TYPES,
        )
        if task is None:
            raise FaceClusterTaskNotFoundError("No active unknown face clustering task")
        return build_face_cluster_status(task)

    def enqueue_rematch(
        self,
        *,
        project_id: int,
        max_faces: int,
        scope: str,
        person_id: Optional[int],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> FaceRematchUnknownResponse:
        settings = get_or_create_project_face_settings(self.db, project_id)
        if not settings.face_recognition_enabled:
            raise FaceRecognitionDisabledError(
                "Face recognition is disabled for this project. "
                "Enable it in face settings first."
            )
        self._validate_rematch_scope(
            scope=scope,
            person_id=person_id,
            start_time=start_time,
            end_time=end_time,
        )

        result = enqueue_face_rematch_unknown_task(
            self.db,
            project_id=project_id,
            max_faces=max_faces,
            scope=scope,
            person_id=person_id,
            start_time=start_time.isoformat() if start_time else None,
            end_time=end_time.isoformat() if end_time else None,
        )
        return FaceRematchUnknownResponse(
            message=(
                "Unknown face rematch queued"
                if result.created
                else "Unknown face rematch already in progress"
            ),
            status=build_face_rematch_status(result.task),
        )

    def rematch_status(self, *, project_id: int) -> FaceRematchUnknownStatusResponse:
        active_task = get_active_face_rematch_task(self.db, project_id)
        if active_task is not None:
            return build_face_rematch_status(active_task)
        return build_face_rematch_status(get_latest_face_rematch_task(self.db, project_id))

    def cancel_rematch(self, *, project_id: int) -> FaceRematchUnknownStatusResponse:
        task = request_project_task_cancel(
            self.db,
            project_id=project_id,
            task_types=FACE_REMATCH_TASK_TYPES,
        )
        if task is None:
            raise FaceRematchTaskNotFoundError("No active unknown face rematch task")
        return build_face_rematch_status(task)

    @staticmethod
    def _validate_rematch_scope(
        *,
        scope: str,
        person_id: Optional[int],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> None:
        if scope == "person" and person_id is None:
            raise FaceRematchValidationError("person_id is required when scope=person")
        if scope == "time_range":
            if start_time is None or end_time is None:
                raise FaceRematchValidationError(
                    "start_time and end_time are required when scope=time_range"
                )
            if start_time > end_time:
                raise FaceRematchValidationError("start_time must be <= end_time")