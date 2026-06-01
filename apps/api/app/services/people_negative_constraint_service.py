from __future__ import annotations

from typing import Collection

from sqlalchemy.orm import Session

from ..models.face import FaceNegativeConstraint


class PeopleNegativeConstraintService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert(
        self,
        *,
        project_id: int,
        face_id: int,
        not_person_id: int,
        source: str,
    ) -> None:
        row = (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id == face_id,
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .first()
        )
        if row is None:
            self._db.add(
                FaceNegativeConstraint(
                    project_id=project_id,
                    face_detection_id=face_id,
                    not_person_id=not_person_id,
                    source=source,
                )
            )
        else:
            row.source = source

    def remove(
        self,
        *,
        project_id: int,
        face_id: int,
        not_person_id: int,
    ) -> None:
        (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id == face_id,
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .delete(synchronize_session=False)
        )

    def upsert_many(
        self,
        *,
        project_id: int,
        pairs: Collection[tuple[int, int]],
        source: str,
    ) -> None:
        unique_pairs = sorted({(int(face_id), int(person_id)) for face_id, person_id in pairs})
        if not unique_pairs:
            return

        face_ids = sorted({face_id for face_id, _ in unique_pairs})
        person_ids = sorted({person_id for _, person_id in unique_pairs})
        existing_rows = (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id.in_(face_ids),
                FaceNegativeConstraint.not_person_id.in_(person_ids),
            )
            .all()
        )
        existing_by_pair = {
            (row.face_detection_id, row.not_person_id): row
            for row in existing_rows
        }

        for face_id, person_id in unique_pairs:
            row = existing_by_pair.get((face_id, person_id))
            if row is None:
                self._db.add(
                    FaceNegativeConstraint(
                        project_id=project_id,
                        face_detection_id=face_id,
                        not_person_id=person_id,
                        source=source,
                    )
                )
            else:
                row.source = source

    def remove_for_person(
        self,
        *,
        project_id: int,
        face_ids: Collection[int],
        not_person_id: int,
    ) -> None:
        unique_face_ids = sorted({int(face_id) for face_id in face_ids})
        if not unique_face_ids:
            return
        (
            self._db.query(FaceNegativeConstraint)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id.in_(unique_face_ids),
                FaceNegativeConstraint.not_person_id == not_person_id,
            )
            .delete(synchronize_session=False)
        )
