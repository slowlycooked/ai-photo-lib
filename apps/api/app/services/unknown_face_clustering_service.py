from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..models.face import FaceDetection, FaceEmbedding, Person, PersonFaceAssignment
from .people_assignment_constants import STATUS_REJECTED, STATUS_REVIEW_PENDING
from .people_learning_service import _coerce_vector, _cosine_similarity
from .project_face_settings_service import get_or_create_project_face_settings


@dataclass(frozen=True)
class UnknownFaceClusteringResult:
    project_id: int
    clusters_created: int
    persons_created: int
    faces_clustered: int
    assignments_created: int
    skipped_reason: Optional[str] = None


@dataclass
class _Cluster:
    centroid: list[float]
    face_ids: list[int]
    vectors: list[list[float]]


def cluster_unknown_faces(
    db: Session,
    *,
    project_id: int,
    max_faces: int = 500,
    photo_ids: Optional[list[int]] = None,
) -> UnknownFaceClusteringResult:
    if not _has_unknown_clustering_tables(db):
        return UnknownFaceClusteringResult(
            project_id=project_id,
            clusters_created=0,
            persons_created=0,
            faces_clustered=0,
            assignments_created=0,
            skipped_reason="missing_people_tables",
        )

    settings = get_or_create_project_face_settings(db, project_id)

    query = (
        db.query(FaceDetection.id, FaceEmbedding.embedding_vector)
        .join(
            FaceEmbedding,
            sa.and_(
                FaceEmbedding.project_id == FaceDetection.project_id,
                FaceEmbedding.face_detection_id == FaceDetection.id,
            ),
        )
        .outerjoin(
            PersonFaceAssignment,
            sa.and_(
                PersonFaceAssignment.project_id == FaceDetection.project_id,
                PersonFaceAssignment.face_detection_id == FaceDetection.id,
                PersonFaceAssignment.assignment_status != STATUS_REJECTED,
            ),
        )
        .filter(
            FaceDetection.project_id == project_id,
            FaceDetection.status == "embedded",
            FaceEmbedding.project_id == project_id,
            FaceEmbedding.model_name == settings.face_embedding_model,
            FaceEmbedding.embedding_vector.isnot(None),
            PersonFaceAssignment.id.is_(None),
        )
    )

    if photo_ids:
        query = query.filter(FaceDetection.photo_id.in_(photo_ids))

    rows = query.order_by(FaceDetection.id.asc()).limit(max_faces).all()

    candidates: list[tuple[int, list[float]]] = []
    for face_id, raw_vector in rows:
        vector = _coerce_vector(raw_vector)
        if not vector:
            continue
        candidates.append((int(face_id), vector))

    if not candidates:
        return UnknownFaceClusteringResult(
            project_id=project_id,
            clusters_created=0,
            persons_created=0,
            faces_clustered=0,
            assignments_created=0,
        )

    clusters: list[_Cluster] = []
    for face_id, vector in candidates:
        best_index = -1
        best_similarity = -1.0
        for i, cluster in enumerate(clusters):
            similarity = _cosine_similarity(vector, cluster.centroid)
            if similarity > best_similarity:
                best_similarity = similarity
                best_index = i

        if best_index >= 0 and best_similarity >= settings.cluster_threshold:
            cluster = clusters[best_index]
            cluster.face_ids.append(face_id)
            cluster.vectors.append(vector)
            cluster.centroid = [
                sum(values) / len(cluster.vectors) for values in zip(*cluster.vectors)
            ]
        else:
            clusters.append(_Cluster(centroid=vector, face_ids=[face_id], vectors=[vector]))

    now = datetime.now(timezone.utc)
    persons_created = 0
    assignments_created = 0

    person_name_seq = (
        db.query(sa.func.count(Person.id))
        .filter(Person.project_id == project_id)
        .scalar()
        or 0
    )

    for cluster in clusters:
        person_name_seq += 1
        person = Person(
            project_id=project_id,
            display_name=f"Cluster Person {person_name_seq}",
            normalized_name=None,
            is_named=False,
            representative_face_detection_id=cluster.face_ids[0],
            sample_count=len(cluster.face_ids),
            confirmed_sample_count=0,
            auto_assigned_count=0,
            review_pending_count=len(cluster.face_ids),
            created_by="system_cluster",
            updated_at=now,
        )
        db.add(person)
        db.flush()
        persons_created += 1

        for face_id in cluster.face_ids:
            assignment = (
                db.query(PersonFaceAssignment)
                .filter(
                    PersonFaceAssignment.project_id == project_id,
                    PersonFaceAssignment.person_id == person.id,
                    PersonFaceAssignment.face_detection_id == face_id,
                )
                .first()
            )
            if assignment is not None:
                continue
            db.add(
                PersonFaceAssignment(
                    project_id=project_id,
                    person_id=person.id,
                    face_detection_id=face_id,
                    assignment_status=STATUS_REVIEW_PENDING,
                    assignment_source="unknown_cluster",
                    confidence=None,
                    similarity_score=None,
                    is_positive_sample=False,
                    is_training_candidate=True,
                    updated_at=now,
                )
            )
            assignments_created += 1

    db.flush()

    return UnknownFaceClusteringResult(
        project_id=project_id,
        clusters_created=len(clusters),
        persons_created=persons_created,
        faces_clustered=len(candidates),
        assignments_created=assignments_created,
    )


def _has_unknown_clustering_tables(db: Session) -> bool:
    try:
        bind = db.get_bind()
        inspector = inspect(bind)
        table_names = set(inspector.get_table_names())
    except Exception:  # noqa: BLE001
        return False
    required = {
        "persons",
        "person_face_assignments",
    }
    return required.issubset(table_names)
