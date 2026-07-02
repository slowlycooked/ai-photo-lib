from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
import json
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..models.face import (
    FaceDetection,
    FaceEmbedding,
    FaceNegativeConstraint,
    Person,
    PersonFaceAssignment,
    PersonPrototype,
)
from .people_assignment_constants import (
    POSITIVE_ASSIGNMENT_STATUSES,
    STATUS_AUTO_ASSIGNED,
    STATUS_REJECTED,
    STATUS_REVIEW_PENDING,
)
from .project_face_settings_service import get_or_create_project_face_settings


@dataclass(frozen=True)
class MatchDecision:
    person_id: int
    similarity: float
    assignment_status: str


def _has_people_learning_tables(db: Session) -> bool:
    engine = db.get_bind()
    inspector = inspect(engine)
    required = {
        "persons",
        "face_embeddings",
        "person_face_assignments",
        "person_prototypes",
    }
    return required.issubset(set(inspector.get_table_names()))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _coerce_vector(raw_vector: object) -> list[float]:
    if raw_vector is None:
        return []
    if isinstance(raw_vector, str):
        try:
            parsed = json.loads(raw_vector)
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(parsed, list):
            return []
        return [float(v) for v in parsed]
    if isinstance(raw_vector, list):
        return [float(v) for v in raw_vector]
    if hasattr(raw_vector, "tolist"):
        try:
            values = raw_vector.tolist()
        except Exception:  # noqa: BLE001
            return []
        if isinstance(values, list):
            return [float(v) for v in values]
        return []
    if hasattr(raw_vector, "__iter__"):
        try:
            return [float(v) for v in raw_vector]  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            return []
    return []


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _refresh_person_counters(db: Session, *, project_id: int, person_id: int) -> None:
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.id == person_id)
        .first()
    )
    if person is None:
        return

    stats = (
        db.query(
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


def rebuild_person_centroid_prototype(
    db: Session,
    *,
    project_id: int,
    person_id: int,
) -> Optional[PersonPrototype]:
    """Build or refresh a single centroid prototype from confirmed positive samples."""
    if not _has_people_learning_tables(db):
        return None

    settings = get_or_create_project_face_settings(db, project_id)

    rows = (
        db.query(
            PersonFaceAssignment.id,
            FaceEmbedding.embedding_vector,
            FaceEmbedding.embedding_dim,
            FaceEmbedding.model_name,
            FaceEmbedding.model_version,
            FaceDetection.face_quality_score,
            PersonFaceAssignment.updated_at,
            FaceEmbedding.embedded_at,
            FaceEmbedding.id,
        )
        .join(
            FaceDetection,
            FaceDetection.id == PersonFaceAssignment.face_detection_id,
        )
        .join(
            FaceEmbedding,
            FaceEmbedding.face_detection_id == FaceDetection.id,
        )
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            PersonFaceAssignment.is_positive_sample.is_(True),
            PersonFaceAssignment.assignment_status.in_(POSITIVE_ASSIGNMENT_STATUSES),
            FaceDetection.project_id == project_id,
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
            sa.or_(
                FaceDetection.face_quality_score.is_(None),
                FaceDetection.face_quality_score >= settings.min_quality_for_prototype,
            ),
        )
        .order_by(FaceEmbedding.embedded_at.desc().nullslast(), FaceEmbedding.id.desc())
        .all()
    )

    # Remove stale centroid when we no longer have usable positive samples.
    if not rows:
        (
            db.query(PersonPrototype)
            .filter(
                PersonPrototype.project_id == project_id,
                PersonPrototype.person_id == person_id,
                PersonPrototype.prototype_type == "centroid",
                PersonPrototype.model_name == settings.face_embedding_model,
            )
            .delete(synchronize_session=False)
        )
        return None

    embedding_dim = int(rows[0][2])
    model_name = str(rows[0][3])
    model_version = str(rows[0][4] or "")
    candidate_rows = [
        row
        for row in rows
        if int(row[2]) == embedding_dim
        and str(row[3]) == model_name
        and str(row[4] or "") == model_version
    ]
    candidate_rows = sorted(
        candidate_rows,
        key=lambda row: (
            float(row[5]) if row[5] is not None else -1.0,
            _coerce_datetime(row[6]),
            int(row[0]),
        ),
        reverse=True,
    )
    sample_limit = int(settings.max_positive_samples_per_person or 0)
    if sample_limit > 0:
        candidate_rows = candidate_rows[:sample_limit]

    vectors: list[list[float]] = []
    assignment_ids: list[int] = []
    for assignment_id, raw_vector, _, _, _, _, _, _, _ in candidate_rows:
        vector = _coerce_vector(raw_vector)
        if len(vector) != embedding_dim:
            continue
        vectors.append(vector)
        assignment_ids.append(int(assignment_id))

    if not vectors:
        return None

    centroid = [sum(values) / len(vectors) for values in zip(*vectors)]

    row = (
        db.query(PersonPrototype)
        .filter(
            PersonPrototype.project_id == project_id,
            PersonPrototype.person_id == person_id,
            PersonPrototype.prototype_type == "centroid",
            PersonPrototype.model_name == model_name,
            PersonPrototype.model_version == model_version,
        )
        .first()
    )
    if row is None:
        row = PersonPrototype(
            project_id=project_id,
            person_id=person_id,
            prototype_type="centroid",
            model_name=model_name,
            model_version=model_version,
            embedding_dim=embedding_dim,
        )
        db.add(row)

    row.embedding_vector = centroid
    row.sample_count = len(vectors)
    row.source_assignment_ids = assignment_ids
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def match_face_detection_to_person(
    db: Session,
    *,
    project_id: int,
    face_detection_id: int,
    target_person_id: Optional[int] = None,
    force_review_pending: bool = False,
    force_auto_assigned: bool = False,
    assignment_source: str = "similarity_match",
) -> Optional[MatchDecision]:
    """Match one face detection against named people prototypes and persist assignment."""
    if not _has_people_learning_tables(db):
        return None

    settings = get_or_create_project_face_settings(db, project_id)

    detection = (
        db.query(FaceDetection)
        .filter(
            FaceDetection.project_id == project_id,
            FaceDetection.id == face_detection_id,
        )
        .first()
    )
    if detection is None:
        return None

    embedding = (
        db.query(FaceEmbedding)
        .filter(
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.face_detection_id == face_detection_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
        )
        .order_by(FaceEmbedding.embedded_at.desc().nullslast(), FaceEmbedding.id.desc())
        .first()
    )
    if embedding is None:
        return None

    target_vector = _coerce_vector(embedding.embedding_vector)
    if not target_vector:
        return None
    embedding_dim = int(embedding.embedding_dim)
    if len(target_vector) != embedding_dim:
        return None
    embedding_model_version = str(embedding.model_version or "")

    candidate_query = (
        db.query(PersonPrototype, Person)
        .join(
            Person,
            sa.and_(
                Person.id == PersonPrototype.person_id,
                Person.project_id == PersonPrototype.project_id,
            ),
        )
        .filter(
            PersonPrototype.project_id == project_id,
            PersonPrototype.prototype_type == "centroid",
            PersonPrototype.model_name == settings.face_embedding_model,
            PersonPrototype.model_version == embedding_model_version,
            PersonPrototype.embedding_dim == embedding_dim,
            PersonPrototype.embedding_vector.isnot(None),
            Person.is_named.is_(True),
        )
    )
    if target_person_id is not None:
        candidate_query = candidate_query.filter(Person.id == int(target_person_id))

    candidate_rows = candidate_query.all()
    if not candidate_rows:
        return None

    negatives: set[int] = set()
    if settings.enable_negative_constraints:
        negatives = {
            row[0]
            for row in (
                db.query(FaceNegativeConstraint.not_person_id)
                .filter(
                    FaceNegativeConstraint.project_id == project_id,
                    FaceNegativeConstraint.face_detection_id == face_detection_id,
                )
                .all()
            )
        }

    best_person_id: Optional[int] = None
    best_similarity = -1.0
    for proto, person in candidate_rows:
        if person.id in negatives:
            continue
        proto_vector = _coerce_vector(proto.embedding_vector)
        similarity = _cosine_similarity(target_vector, proto_vector)
        if similarity > best_similarity:
            best_similarity = similarity
            best_person_id = int(person.id)

    if best_person_id is None:
        return None

    assignment_status: Optional[str] = None
    if force_auto_assigned and best_similarity >= settings.review_threshold:
        assignment_status = STATUS_AUTO_ASSIGNED
    elif (
        not force_review_pending
        and best_similarity >= settings.auto_accept_threshold
        and settings.allow_auto_assignment
    ):
        assignment_status = STATUS_AUTO_ASSIGNED
    elif best_similarity >= settings.review_threshold:
        assignment_status = STATUS_REVIEW_PENDING

    if assignment_status is None:
        return None

    assignment = (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == best_person_id,
            PersonFaceAssignment.face_detection_id == face_detection_id,
        )
        .first()
    )
    if assignment is None:
        assignment = PersonFaceAssignment(
            project_id=project_id,
            person_id=best_person_id,
            face_detection_id=face_detection_id,
            assignment_status=assignment_status,
            assignment_source=assignment_source,
        )
        db.add(assignment)

    assignment.assignment_status = assignment_status
    assignment.assignment_source = assignment_source
    assignment.confidence = float(best_similarity)
    assignment.similarity_score = float(best_similarity)
    assignment.is_positive_sample = False
    assignment.is_training_candidate = assignment_status in {"auto_assigned", "review_pending"}
    assignment.updated_at = datetime.now(timezone.utc)

    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.id == best_person_id)
        .first()
    )
    if person and person.representative_face_detection_id is None:
        person.representative_face_detection_id = face_detection_id

    db.flush()
    _refresh_person_counters(db, project_id=project_id, person_id=best_person_id)

    return MatchDecision(
        person_id=best_person_id,
        similarity=float(best_similarity),
        assignment_status=assignment_status,
    )
