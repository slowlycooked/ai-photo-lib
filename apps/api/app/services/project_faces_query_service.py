from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceEmbedding, Person, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_HUMAN_CONFIRMED,
    STATUS_HUMAN_CORRECTED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)


class FaceNotFoundError(RuntimeError):
    pass


class FaceCropNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class FaceAssignmentInfo:
    """Best non-rejected person assignment for a face, for display purposes."""

    person_id: int
    person_display_name: str
    assignment_status: str
    assignment_source: Optional[str]


_ASSIGNMENT_STATUS_RANK: dict[str, int] = {
    STATUS_HUMAN_CONFIRMED: 0,
    STATUS_HUMAN_CORRECTED: 0,
    STATUS_AUTO_ASSIGNED: 1,
    STATUS_REVIEW_PENDING: 2,
}


@dataclass
class ProjectFacesQueryService:
    db: Session

    def list_faces(
        self,
        *,
        project_id: int,
        page: int,
        page_size: int,
        photo_id: Optional[int],
        status: Optional[str],
    ) -> tuple[int, list[FaceDetection]]:
        page_size = max(1, min(page_size, 200))
        offset = (page - 1) * page_size

        query = self.db.query(FaceDetection).filter(FaceDetection.project_id == project_id)
        if photo_id is not None:
            query = query.filter(FaceDetection.photo_id == photo_id)
        if status is not None:
            query = query.filter(FaceDetection.status == status)

        total = query.count()
        items = (
            query.order_by(FaceDetection.detected_at.desc().nullslast(), FaceDetection.id.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return total, items

    def get_face_detail(
        self,
        *,
        project_id: int,
        face_id: int,
    ) -> tuple[FaceDetection, list[FaceEmbedding]]:
        face = (
            self.db.query(FaceDetection)
            .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
            .first()
        )
        if face is None:
            raise FaceNotFoundError("Face not found in project")

        embeddings = (
            self.db.query(FaceEmbedding)
            .filter(
                FaceEmbedding.project_id == project_id,
                FaceEmbedding.face_detection_id == face_id,
            )
            .order_by(FaceEmbedding.created_at.desc(), FaceEmbedding.id.desc())
            .all()
        )
        return face, embeddings

    def get_active_assignments_for_faces(
        self,
        *,
        project_id: int,
        face_ids: list[int],
    ) -> dict[int, FaceAssignmentInfo]:
        """Return the best non-rejected assignment per face, project-scoped.

        Priority: human_confirmed/human_corrected > auto_assigned > review_pending;
        ties break on latest updated_at, then highest assignment id.
        """
        if not face_ids:
            return {}
        rows = (
            self.db.query(
                PersonFaceAssignment.face_detection_id,
                PersonFaceAssignment.id,
                PersonFaceAssignment.person_id,
                PersonFaceAssignment.assignment_status,
                PersonFaceAssignment.assignment_source,
                PersonFaceAssignment.updated_at,
                Person.display_name,
            )
            .join(Person, Person.id == PersonFaceAssignment.person_id)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .all()
        )
        best: dict[int, tuple[tuple[int, str, int], FaceAssignmentInfo]] = {}
        for row in rows:
            face_id = int(row.face_detection_id)
            status = str(row.assignment_status or "")
            rank = (
                _ASSIGNMENT_STATUS_RANK.get(status, 3),
                str(row.updated_at or ""),
                int(row.id),
            )
            info = FaceAssignmentInfo(
                person_id=int(row.person_id),
                person_display_name=str(row.display_name),
                assignment_status=status,
                assignment_source=(
                    str(row.assignment_source) if row.assignment_source else None
                ),
            )
            current = best.get(face_id)
            if current is None or rank > current[0]:
                best[face_id] = (rank, info)
        return {face_id: info for face_id, (_, info) in best.items()}

    def get_face_crop_path(self, *, project_id: int, face_id: int) -> Path:
        face = (
            self.db.query(FaceDetection)
            .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
            .first()
        )
        if face is None:
            raise FaceNotFoundError("Face not found in project")
        if not face.face_crop_path:
            raise FaceCropNotFoundError("Face crop not stored for this detection")
        crop_path = Path(face.face_crop_path)
        if not crop_path.exists():
            raise FaceCropNotFoundError("Face crop file not found")
        return crop_path