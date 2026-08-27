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


@dataclass(frozen=True)
class PersonSearchProfile:
    project_id: int
    person_id: int
    embedding_vector: list[float]
    embedding_dim: int
    model_name: str
    model_version: str
    sample_count: int
    source: str


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


def build_person_search_profile(
    db: Session,
    *,
    project_id: int,
    person_id: int,
) -> Optional[PersonSearchProfile]:
    """Build a non-persistent search profile, falling back to confirmed samples."""
    if not _has_people_learning_tables(db):
        return None

    settings = get_or_create_project_face_settings(db, project_id)
    person = (
        db.query(Person)
        .filter(
            Person.project_id == project_id,
            Person.id == person_id,
            Person.is_named.is_(True),
        )
        .first()
    )
    if person is None:
        return None

    prototype = (
        db.query(PersonPrototype)
        .filter(
            PersonPrototype.project_id == project_id,
            PersonPrototype.person_id == person_id,
            PersonPrototype.prototype_type == "centroid",
            PersonPrototype.model_name == settings.face_embedding_model,
            PersonPrototype.embedding_vector.isnot(None),
        )
        .order_by(PersonPrototype.updated_at.desc(), PersonPrototype.id.desc())
        .first()
    )
    if prototype is not None:
        vector = _coerce_vector(prototype.embedding_vector)
        if len(vector) == int(prototype.embedding_dim):
            return PersonSearchProfile(
                project_id=project_id,
                person_id=person_id,
                embedding_vector=vector,
                embedding_dim=int(prototype.embedding_dim),
                model_name=str(prototype.model_name),
                model_version=str(prototype.model_version or ""),
                sample_count=int(prototype.sample_count or 0),
                source="centroid",
            )

    rows = (
        db.query(
            FaceEmbedding.embedding_vector,
            FaceEmbedding.embedding_dim,
            FaceEmbedding.model_name,
            FaceEmbedding.model_version,
            FaceDetection.face_quality_score,
            PersonFaceAssignment.updated_at,
            FaceEmbedding.id,
        )
        .join(FaceDetection, FaceDetection.id == PersonFaceAssignment.face_detection_id)
        .join(FaceEmbedding, FaceEmbedding.face_detection_id == FaceDetection.id)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            PersonFaceAssignment.is_positive_sample.is_(True),
            PersonFaceAssignment.assignment_status.in_(POSITIVE_ASSIGNMENT_STATUSES),
            FaceDetection.project_id == project_id,
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
        )
        .order_by(
            FaceDetection.face_quality_score.desc().nullslast(),
            PersonFaceAssignment.updated_at.desc(),
            FaceEmbedding.id.desc(),
        )
        .all()
    )
    if not rows:
        return None

    embedding_dim = int(rows[0][1])
    model_name = str(rows[0][2])
    model_version = str(rows[0][3] or "")
    vectors = [
        vector
        for row in rows[: int(settings.max_positive_samples_per_person or len(rows))]
        if int(row[1]) == embedding_dim
        and str(row[2]) == model_name
        and str(row[3] or "") == model_version
        and len(vector := _coerce_vector(row[0])) == embedding_dim
    ]
    if not vectors:
        return None

    return PersonSearchProfile(
        project_id=project_id,
        person_id=person_id,
        embedding_vector=[sum(values) / len(vectors) for values in zip(*vectors)],
        embedding_dim=embedding_dim,
        model_name=model_name,
        model_version=model_version,
        sample_count=len(vectors),
        source="confirmed_sample_fallback",
    )


def _load_candidate_prototypes(
    db: Session,
    *,
    project_id: int,
    model_name: str,
    model_version: str,
    embedding_dim: int,
    target_person_id: Optional[int],
) -> list[tuple[PersonPrototype, Person]]:
    query = (
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
            PersonPrototype.model_name == model_name,
            PersonPrototype.model_version == model_version,
            PersonPrototype.embedding_dim == embedding_dim,
            PersonPrototype.embedding_vector.isnot(None),
            Person.is_named.is_(True),
        )
    )
    if target_person_id is not None:
        query = query.filter(Person.id == int(target_person_id))
    return query.all()


def _load_negative_person_ids(
    db: Session,
    *,
    project_id: int,
    face_detection_id: int,
    enabled: bool,
) -> set[int]:
    if not enabled:
        return set()
    return {
        int(row[0])
        for row in (
            db.query(FaceNegativeConstraint.not_person_id)
            .filter(
                FaceNegativeConstraint.project_id == project_id,
                FaceNegativeConstraint.face_detection_id == face_detection_id,
            )
            .all()
        )
    }


def _search_profile_matches_embedding(
    profile: PersonSearchProfile,
    *,
    project_id: int,
    target_person_id: Optional[int],
    model_name: str,
    model_version: str,
    embedding_dim: int,
) -> bool:
    return (
        target_person_id is not None
        and profile.project_id == project_id
        and profile.person_id == int(target_person_id)
        and profile.model_name == model_name
        and profile.model_version == model_version
        and profile.embedding_dim == embedding_dim
    )


def _best_prototype_match(
    target_vector: list[float],
    candidate_rows: list[tuple[PersonPrototype, Person]],
    negatives: set[int],
) -> tuple[Optional[int], float]:
    best_person_id: Optional[int] = None
    best_similarity = -1.0
    for prototype, person in candidate_rows:
        if person.id in negatives:
            continue
        similarity = _cosine_similarity(
            target_vector,
            _coerce_vector(prototype.embedding_vector),
        )
        if similarity > best_similarity:
            best_similarity = similarity
            best_person_id = int(person.id)
    return best_person_id, best_similarity


def _resolve_match_candidate(
    db: Session,
    *,
    project_id: int,
    face_detection_id: int,
    target_vector: list[float],
    embedding_dim: int,
    model_name: str,
    model_version: str,
    negative_constraints_enabled: bool,
    target_person_id: Optional[int],
    target_search_profile: Optional[PersonSearchProfile],
) -> tuple[Optional[int], float]:
    negatives = _load_negative_person_ids(
        db,
        project_id=project_id,
        face_detection_id=face_detection_id,
        enabled=negative_constraints_enabled,
    )
    if target_search_profile is not None:
        if not _search_profile_matches_embedding(
            target_search_profile,
            project_id=project_id,
            target_person_id=target_person_id,
            model_name=model_name,
            model_version=model_version,
            embedding_dim=embedding_dim,
        ):
            return None, -1.0
        if target_search_profile.person_id in negatives:
            return None, -1.0
        return (
            target_search_profile.person_id,
            _cosine_similarity(target_vector, target_search_profile.embedding_vector),
        )

    candidate_rows = _load_candidate_prototypes(
        db,
        project_id=project_id,
        model_name=model_name,
        model_version=model_version,
        embedding_dim=embedding_dim,
        target_person_id=target_person_id,
    )
    if not candidate_rows:
        return None, -1.0
    return _best_prototype_match(target_vector, candidate_rows, negatives)


def match_face_detection_to_person(
    db: Session,
    *,
    project_id: int,
    face_detection_id: int,
    target_person_id: Optional[int] = None,
    target_search_profile: Optional[PersonSearchProfile] = None,
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

    best_person_id, best_similarity = _resolve_match_candidate(
        db,
        project_id=project_id,
        face_detection_id=face_detection_id,
        target_vector=target_vector,
        embedding_dim=embedding_dim,
        model_name=settings.face_embedding_model,
        model_version=embedding_model_version,
        negative_constraints_enabled=bool(settings.enable_negative_constraints),
        target_person_id=target_person_id,
        target_search_profile=target_search_profile,
    )

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
