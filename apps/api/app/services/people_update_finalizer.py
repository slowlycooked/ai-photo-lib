from __future__ import annotations

from datetime import datetime, timezone
from typing import Collection

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.face import Person, PersonFaceAssignment
from .people_assignment_constants import (
    STATUS_AUTO_ASSIGNED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .people_learning_service import rebuild_person_centroid_prototype


class PeopleUpdateFinalizer:
    def __init__(self, db: Session) -> None:
        self._db = db

    def finalize(
        self,
        *,
        project_id: int,
        person_ids: Collection[int],
    ) -> None:
        self._db.flush()
        for person_id in sorted({int(person_id) for person_id in person_ids}):
            self.refresh_person_counters(project_id=project_id, person_id=person_id)
            rebuild_person_centroid_prototype(
                self._db,
                project_id=project_id,
                person_id=person_id,
            )

    def refresh_person_counters(self, *, project_id: int, person_id: int) -> None:
        person = (
            self._db.query(Person)
            .filter(Person.project_id == project_id, Person.id == person_id)
            .first()
        )
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found in project")

        stats = (
            self._db.query(
                sa.func.count(PersonFaceAssignment.id),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.is_positive_sample.is_(True), 1), else_=0)
                ),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.assignment_status == STATUS_AUTO_ASSIGNED, 1), else_=0)
                ),
                sa.func.sum(
                    sa.case((PersonFaceAssignment.assignment_status == STATUS_REVIEW_PENDING, 1), else_=0)
                ),
            )
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            )
            .one()
        )
        person.sample_count = int(stats[0] or 0)
        person.confirmed_sample_count = int(stats[1] or 0)
        person.auto_assigned_count = int(stats[2] or 0)
        person.review_pending_count = int(stats[3] or 0)
        person.updated_at = datetime.now(timezone.utc)
