from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, Person


class PeopleLookupService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_person_or_404(self, project_id: int, person_id: int) -> Person:
        person = (
            self._db.query(Person)
            .filter(Person.project_id == project_id, Person.id == person_id)
            .first()
        )
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found in project")
        return person

    def get_face_or_404(self, project_id: int, face_id: int) -> FaceDetection:
        face = (
            self._db.query(FaceDetection)
            .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
            .first()
        )
        if face is None:
            raise HTTPException(status_code=404, detail="Face not found in project")
        return face
