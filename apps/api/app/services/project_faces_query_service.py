from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceEmbedding


class FaceNotFoundError(RuntimeError):
    pass


class FaceCropNotFoundError(RuntimeError):
    pass


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