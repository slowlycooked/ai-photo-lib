"""People recall service for project-scoped search.

Builds candidate photos from person-face assignments and face detections.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set

from sqlalchemy.orm import Session

from ...models.face import FaceDetection, Person, PersonFaceAssignment
from ..person_name_tags import extract_person_name_tags
from ..people_assignment_constants import (
    ASSIGNMENT_STATUS_WEIGHT,
    SEARCH_RECALL_ASSIGNMENT_STATUSES,
)
from .people_query_resolver import PeopleQueryResolution
from .types import SearchCandidate


@dataclass(frozen=True)
class PeopleRecallResult:
    candidates: List[SearchCandidate]
    photo_ids: Set[int]
    matched_person_ids: List[int]


class PeopleRecallService:
    """Recall photos that contain one or more named people in current project."""

    def __init__(self, db: Session, project_id: int) -> None:
        self._db = db
        self._project_id = project_id

    def recall(
        self,
        *,
        resolution: PeopleQueryResolution,
        constrained_photo_ids: Optional[Set[int]] = None,
        assignment_statuses: Sequence[str] = SEARCH_RECALL_ASSIGNMENT_STATUSES,
        limit: int = 5000,
    ) -> PeopleRecallResult:
        if not resolution.matched_person_ids:
            return PeopleRecallResult(candidates=[], photo_ids=set(), matched_person_ids=[])

        statuses = [s for s in assignment_statuses if s in SEARCH_RECALL_ASSIGNMENT_STATUSES]
        if not statuses:
            statuses = list(SEARCH_RECALL_ASSIGNMENT_STATUSES)

        query = (
            self._db.query(
                FaceDetection.photo_id,
                PersonFaceAssignment.person_id,
                Person.display_name,
                PersonFaceAssignment.assignment_status,
                PersonFaceAssignment.confidence,
                PersonFaceAssignment.similarity_score,
                PersonFaceAssignment.face_detection_id,
            )
            .join(
                FaceDetection,
                FaceDetection.id == PersonFaceAssignment.face_detection_id,
            )
            .join(
                Person,
                Person.id == PersonFaceAssignment.person_id,
            )
            .filter(
                PersonFaceAssignment.project_id == self._project_id,
                FaceDetection.project_id == self._project_id,
                Person.project_id == self._project_id,
                PersonFaceAssignment.person_id.in_(resolution.matched_person_ids),
                PersonFaceAssignment.assignment_status.in_(statuses),
            )
        )

        if constrained_photo_ids is not None:
            if not constrained_photo_ids:
                return PeopleRecallResult(
                    candidates=[],
                    photo_ids=set(),
                    matched_person_ids=list(resolution.matched_person_ids),
                )
            query = query.filter(FaceDetection.photo_id.in_(constrained_photo_ids))

        rows = query.limit(limit).all()

        photo_people: Dict[int, List[dict]] = defaultdict(list)
        photo_person_set: Dict[int, Set[int]] = defaultdict(set)
        for row in rows:
            photo_id = int(row.photo_id)
            person_id = int(row.person_id)
            photo_person_set[photo_id].add(person_id)
            photo_people[photo_id].append(
                {
                    "person_id": person_id,
                    "display_name": str(row.display_name),
                    "name_tags": extract_person_name_tags(str(row.display_name)),
                    "assignment_status": str(row.assignment_status),
                    "confidence": float(row.confidence) if row.confidence is not None else None,
                    "similarity_score": (
                        float(row.similarity_score) if row.similarity_score is not None else None
                    ),
                    "face_detection_id": int(row.face_detection_id),
                }
            )

        required_ids = set(resolution.matched_person_ids)
        candidates: List[SearchCandidate] = []
        for photo_id, matched in photo_people.items():
            present_ids = photo_person_set.get(photo_id, set())
            if resolution.people_filter_mode == "all":
                if not required_ids.issubset(present_ids):
                    continue
                matched_for_score = [m for m in matched if int(m["person_id"]) in required_ids]
            else:
                matched_for_score = [m for m in matched if int(m["person_id"]) in required_ids]
                if not matched_for_score:
                    continue

            score = self._compute_people_score(matched_for_score, len(required_ids))
            candidates.append(
                SearchCandidate(
                    photo_id=photo_id,
                    people_score=score,
                    final_score=score,
                    match_source=["people"],
                    people_explain={
                        "matched_people": matched_for_score,
                        "people_filter_mode": resolution.people_filter_mode,
                    },
                )
            )

        candidates.sort(key=lambda c: c.people_score, reverse=True)
        for rank, candidate in enumerate(candidates, start=1):
            candidate.people_rank = rank

        return PeopleRecallResult(
            candidates=candidates,
            photo_ids={c.photo_id for c in candidates},
            matched_person_ids=list(resolution.matched_person_ids),
        )

    @staticmethod
    def _compute_people_score(matched_people: List[dict], required_count: int) -> float:
        if not matched_people:
            return 0.0

        weighted = 0.0
        for row in matched_people:
            status = str(row.get("assignment_status") or "")
            status_weight = ASSIGNMENT_STATUS_WEIGHT.get(status, 0.0)
            confidence = row.get("confidence")
            similarity = row.get("similarity_score")
            confidence_v = float(confidence) if confidence is not None else 0.0
            similarity_v = float(similarity) if similarity is not None else 0.0
            evidence_score = (confidence_v * 0.7) + (similarity_v * 0.3)
            weighted += status_weight * max(evidence_score, 0.2)

        coverage = min(1.0, len({int(r["person_id"]) for r in matched_people}) / max(1, required_count))
        return round(weighted + (coverage * 0.2), 6)
