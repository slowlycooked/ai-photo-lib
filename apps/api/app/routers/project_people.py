from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..logging_config import request_id_ctx
from ..models.face import FaceDetection, FaceNegativeConstraint, Person, PersonFaceAssignment
from ..models.project import Project
from ..schemas.face import (
    PersonActionResponse,
    PersonBatchActionResponse,
    PersonBatchMoveRequest,
    PersonBatchMoveResponse,
    PersonBatchReviewRequest,
    FaceDetectionResponse,
    PersonCreateRequest,
    PersonDetailResponse,
    PersonFaceMoveRequest,
    PersonFaceAssignmentResponse,
    PersonListResponse,
    PersonMergeRequest,
    PersonMergeResponse,
    PersonMoveFaceResponse,
    PersonRenameRequest,
    PersonReviewListResponse,
    PersonRepresentativeFaceRequest,
    PersonSplitRequest,
    PersonSplitResponse,
    PersonSummaryResponse,
)
from ..services.people_learning_service import rebuild_person_centroid_prototype

router = APIRouter(prefix="/projects", tags=["project-people"])
logger = logging.getLogger(__name__)

_BATCH_RETRYABLE_DB_ERRORS = (OperationalError, DBAPIError)


def _get_person_or_404(db: Session, project_id: int, person_id: int) -> Person:
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.id == person_id)
        .first()
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found in project")
    return person


def _get_face_or_404(db: Session, project_id: int, face_id: int) -> FaceDetection:
    face = (
        db.query(FaceDetection)
        .filter(FaceDetection.project_id == project_id, FaceDetection.id == face_id)
        .first()
    )
    if face is None:
        raise HTTPException(status_code=404, detail="Face not found in project")
    return face


def _get_assignment(
    db: Session,
    *,
    project_id: int,
    person_id: int,
    face_id: int,
) -> PersonFaceAssignment | None:
    return (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            PersonFaceAssignment.face_detection_id == face_id,
        )
        .first()
    )


def _upsert_negative_constraint(
    db: Session,
    *,
    project_id: int,
    face_id: int,
    not_person_id: int,
    source: str,
) -> None:
    row = (
        db.query(FaceNegativeConstraint)
        .filter(
            FaceNegativeConstraint.project_id == project_id,
            FaceNegativeConstraint.face_detection_id == face_id,
            FaceNegativeConstraint.not_person_id == not_person_id,
        )
        .first()
    )
    if row is None:
        db.add(
            FaceNegativeConstraint(
                project_id=project_id,
                face_detection_id=face_id,
                not_person_id=not_person_id,
                source=source,
            )
        )
    else:
        row.source = source


def _remove_negative_constraint(
    db: Session,
    *,
    project_id: int,
    face_id: int,
    not_person_id: int,
) -> None:
    (
        db.query(FaceNegativeConstraint)
        .filter(
            FaceNegativeConstraint.project_id == project_id,
            FaceNegativeConstraint.face_detection_id == face_id,
            FaceNegativeConstraint.not_person_id == not_person_id,
        )
        .delete(synchronize_session=False)
    )


def _refresh_person_counters(db: Session, *, project_id: int, person_id: int) -> None:
    person = _get_person_or_404(db, project_id, person_id)
    stats = (
        db.query(
            sa.func.count(PersonFaceAssignment.id),
            sa.func.sum(
                sa.case((PersonFaceAssignment.is_positive_sample.is_(True), 1), else_=0)
            ),
            sa.func.sum(
                sa.case((PersonFaceAssignment.assignment_status == "auto_assigned", 1), else_=0)
            ),
            sa.func.sum(
                sa.case((PersonFaceAssignment.assignment_status == "review_pending", 1), else_=0)
            ),
        )
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            PersonFaceAssignment.assignment_status != "rejected",
        )
        .one()
    )
    person.sample_count = int(stats[0] or 0)
    person.confirmed_sample_count = int(stats[1] or 0)
    person.auto_assigned_count = int(stats[2] or 0)
    person.review_pending_count = int(stats[3] or 0)
    person.updated_at = datetime.now(timezone.utc)


def _serialize_assignment(
    assignment: PersonFaceAssignment,
    face_detection: FaceDetection,
) -> PersonFaceAssignmentResponse:
    return PersonFaceAssignmentResponse(
        id=assignment.id,
        project_id=assignment.project_id,
        person_id=assignment.person_id,
        face_detection_id=assignment.face_detection_id,
        assignment_status=assignment.assignment_status,
        assignment_source=assignment.assignment_source,
        confidence=assignment.confidence,
        similarity_score=assignment.similarity_score,
        is_positive_sample=assignment.is_positive_sample,
        is_training_candidate=assignment.is_training_candidate,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
        face_detection=FaceDetectionResponse.model_validate(face_detection),
    )


def _resolve_batch_audit_fields(
    request: Request,
    *,
    body_request_id: Optional[str],
    body_operator: Optional[str],
    header_operator: Optional[str],
) -> tuple[Optional[str], str]:
    request_id = (
        body_request_id
        or request.headers.get("x-request-id")
        or request_id_ctx.get()
    )
    if request_id is not None:
        request_id = request_id.strip()[:128] or None

    operator = (
        body_operator
        or header_operator
        or request.headers.get("x-operator")
        or "unknown"
    )
    operator = operator.strip()[:128] or "unknown"
    return request_id, operator


def _execute_batch_with_retry(
    db: Session,
    *,
    operation_name: str,
    request_id: Optional[str],
    operator: str,
    max_attempts: int,
    fn,
) -> tuple[object, int]:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(), attempt
        except _BATCH_RETRYABLE_DB_ERRORS as exc:
            db.rollback()
            last_error = exc
            logger.warning(
                "%s.retryable_db_error request_id=%s operator=%s attempt=%d/%d error=%s",
                operation_name,
                request_id,
                operator,
                attempt,
                max_attempts,
                exc,
            )

    raise HTTPException(
        status_code=503,
        detail=(
            f"{operation_name} failed after {max_attempts} attempts due to retryable database errors"
            + (f": {last_error}" if last_error else "")
        ),
    )


@router.get("/{project_id}/people/review", response_model=PersonReviewListResponse)
def list_project_review_pending(
    project_id: int,
    person_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonReviewListResponse:
    query = (
        db.query(PersonFaceAssignment, FaceDetection)
        .join(
            FaceDetection,
            FaceDetection.id == PersonFaceAssignment.face_detection_id,
        )
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.assignment_status == "review_pending",
            FaceDetection.project_id == project_id,
        )
    )

    if person_id is not None:
        _get_person_or_404(db, project_id, person_id)
        query = query.filter(PersonFaceAssignment.person_id == person_id)

    total = query.count()
    rows = (
        query.order_by(
            PersonFaceAssignment.updated_at.desc(),
            PersonFaceAssignment.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PersonReviewListResponse(
        total=total,
        items=[_serialize_assignment(assignment, face_detection) for assignment, face_detection in rows],
    )


@router.get("/{project_id}/people", response_model=PersonListResponse)
def list_project_people(
    project_id: int,
    include_unnamed: bool = True,
    is_named: Optional[bool] = None,
    has_review_pending: Optional[bool] = None,
    min_sample_count: Optional[int] = Query(default=None, ge=0),
    min_auto_assigned_count: Optional[int] = Query(default=None, ge=0),
    q: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(200, ge=1, le=500),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonListResponse:
    query = db.query(Person).filter(Person.project_id == project_id)

    if is_named is not None:
        query = query.filter(Person.is_named.is_(is_named))
    elif not include_unnamed:
        query = query.filter(Person.is_named.is_(True))

    if has_review_pending is not None:
        if has_review_pending:
            query = query.filter(Person.review_pending_count > 0)
        else:
            query = query.filter(Person.review_pending_count == 0)

    if min_sample_count is not None:
        query = query.filter(Person.sample_count >= min_sample_count)

    if min_auto_assigned_count is not None:
        query = query.filter(Person.auto_assigned_count >= min_auto_assigned_count)

    if q:
        q_term = q.strip()
        if q_term:
            like_term = f"%{q_term}%"
            query = query.filter(
                sa.or_(
                    Person.display_name.ilike(like_term),
                    Person.normalized_name.ilike(like_term.lower()),
                )
            )

    total = query.count()
    people = (
        query.order_by(
            Person.is_named.desc(),
            Person.confirmed_sample_count.desc(),
            Person.sample_count.desc(),
            Person.updated_at.desc(),
            Person.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return PersonListResponse(
        total=total,
        items=[PersonSummaryResponse.model_validate(person) for person in people],
    )


@router.post("/{project_id}/people", response_model=PersonActionResponse)
def create_project_person(
    project_id: int,
    body: PersonCreateRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    now = datetime.now(timezone.utc)
    display_name = (body.display_name or "").strip()
    if not display_name:
        display_name = f"Person {now.strftime('%Y%m%d%H%M%S')}"

    is_named = bool(body.is_named and display_name)
    person = Person(
        project_id=project_id,
        display_name=display_name,
        normalized_name=display_name.lower() if is_named else None,
        is_named=is_named,
        representative_face_detection_id=None,
        sample_count=0,
        confirmed_sample_count=0,
        auto_assigned_count=0,
        review_pending_count=0,
        created_by="human_created",
        updated_at=now,
    )
    db.add(person)
    db.commit()
    db.refresh(person)
    logger.info(
        "people.create project_id=%d person_id=%d display_name=%s",
        project_id,
        person.id,
        display_name,
    )
    return PersonActionResponse(person=PersonSummaryResponse.model_validate(person))


@router.get("/{project_id}/people/{person_id}", response_model=PersonDetailResponse)
def get_project_person(
    project_id: int,
    person_id: int,
    assignment_limit: int = Query(120, ge=1, le=500),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonDetailResponse:
    person = (
        db.query(Person)
        .filter(Person.project_id == project_id, Person.id == person_id)
        .first()
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found in project")

    rows = (
        db.query(PersonFaceAssignment, FaceDetection)
        .join(
            FaceDetection,
            FaceDetection.id == PersonFaceAssignment.face_detection_id,
        )
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            FaceDetection.project_id == project_id,
        )
        .order_by(
            PersonFaceAssignment.is_positive_sample.desc(),
            PersonFaceAssignment.updated_at.desc(),
            PersonFaceAssignment.id.desc(),
        )
        .limit(assignment_limit)
        .all()
    )

    payload = PersonDetailResponse.model_validate(person)
    payload.assignments = [
        PersonFaceAssignmentResponse(
            id=assignment.id,
            project_id=assignment.project_id,
            person_id=assignment.person_id,
            face_detection_id=assignment.face_detection_id,
            assignment_status=assignment.assignment_status,
            assignment_source=assignment.assignment_source,
            confidence=assignment.confidence,
            similarity_score=assignment.similarity_score,
            is_positive_sample=assignment.is_positive_sample,
            is_training_candidate=assignment.is_training_candidate,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            face_detection=FaceDetectionResponse.model_validate(face_detection),
        )
        for assignment, face_detection in rows
    ]
    return payload


@router.patch("/{project_id}/people/{person_id}", response_model=PersonActionResponse)
def rename_project_person(
    project_id: int,
    person_id: int,
    body: PersonRenameRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    person = _get_person_or_404(db, project_id, person_id)
    display_name = body.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name cannot be empty")
    person.display_name = display_name
    person.normalized_name = display_name.lower()
    person.is_named = True
    person.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(person)
    logger.info(
        "people.rename project_id=%d person_id=%d display_name=%s",
        project_id,
        person_id,
        display_name,
    )
    return PersonActionResponse(person=PersonSummaryResponse.model_validate(person))


@router.delete("/{project_id}/people/{person_id}", response_model=dict)
def delete_project_person(
    project_id: int,
    person_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> dict:
    person = _get_person_or_404(db, project_id, person_id)

    active_assignment_count = (
        db.query(sa.func.count(PersonFaceAssignment.id))
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
            PersonFaceAssignment.assignment_status != "rejected",
        )
        .scalar()
        or 0
    )
    if int(active_assignment_count) > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete person with active assignments. "
                "Move or reject active faces first."
            ),
        )

    (
        db.query(FaceNegativeConstraint)
        .filter(
            FaceNegativeConstraint.project_id == project_id,
            FaceNegativeConstraint.not_person_id == person_id,
        )
        .delete(synchronize_session=False)
    )
    (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == person_id,
        )
        .delete(synchronize_session=False)
    )

    db.delete(person)
    db.commit()
    logger.info(
        "people.delete project_id=%d person_id=%d",
        project_id,
        person_id,
    )
    return {"deleted": True, "message": "Person deleted"}


@router.post(
    "/{project_id}/people/{source_person_id}/merge",
    response_model=PersonMergeResponse,
)
def merge_project_persons(
    project_id: int,
    source_person_id: int,
    body: PersonMergeRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonMergeResponse:
    source_person = _get_person_or_404(db, project_id, source_person_id)
    target_person = _get_person_or_404(db, project_id, body.target_person_id)
    if source_person.id == target_person.id:
        raise HTTPException(status_code=422, detail="target_person_id must be different")

    now = datetime.now(timezone.utc)
    source_assignments = (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == source_person.id,
            PersonFaceAssignment.assignment_status != "rejected",
        )
        .all()
    )

    moved_assignments = 0
    for assignment in source_assignments:
        target_assignment = _get_assignment(
            db,
            project_id=project_id,
            person_id=target_person.id,
            face_id=assignment.face_detection_id,
        )
        if target_assignment is None:
            assignment.person_id = target_person.id
            assignment.assignment_source = "human_merge"
            assignment.updated_at = now
            moved_assignments += 1
            continue

        if target_assignment.assignment_status == "rejected":
            target_assignment.assignment_status = assignment.assignment_status
            target_assignment.assignment_source = "human_merge"
            target_assignment.confidence = assignment.confidence
            target_assignment.similarity_score = assignment.similarity_score
            target_assignment.is_positive_sample = assignment.is_positive_sample
            target_assignment.is_training_candidate = assignment.is_training_candidate
            target_assignment.updated_at = now

        assignment.assignment_status = "rejected"
        assignment.assignment_source = "human_merge"
        assignment.is_positive_sample = False
        assignment.is_training_candidate = False
        assignment.updated_at = now

    if target_person.representative_face_detection_id is None:
        target_person.representative_face_detection_id = source_person.representative_face_detection_id
    source_person.representative_face_detection_id = None
    source_person.updated_at = now
    target_person.updated_at = now

    db.flush()
    _refresh_person_counters(db, project_id=project_id, person_id=source_person.id)
    _refresh_person_counters(db, project_id=project_id, person_id=target_person.id)
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=source_person.id,
    )
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=target_person.id,
    )

    db.commit()
    db.refresh(source_person)
    db.refresh(target_person)
    logger.info(
        "people.merge project_id=%d source_person_id=%d target_person_id=%d moved=%d",
        project_id,
        source_person.id,
        target_person.id,
        moved_assignments,
    )
    return PersonMergeResponse(
        moved_assignments=moved_assignments,
        source_person=PersonSummaryResponse.model_validate(source_person),
        target_person=PersonSummaryResponse.model_validate(target_person),
    )


@router.post(
    "/{project_id}/people/{person_id}/split",
    response_model=PersonSplitResponse,
)
def split_project_person(
    project_id: int,
    person_id: int,
    body: PersonSplitRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonSplitResponse:
    source_person = _get_person_or_404(db, project_id, person_id)
    now = datetime.now(timezone.utc)
    face_ids = sorted({int(face_id) for face_id in body.face_detection_ids})

    source_assignments = (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.person_id == source_person.id,
            PersonFaceAssignment.face_detection_id.in_(face_ids),
            PersonFaceAssignment.assignment_status != "rejected",
        )
        .all()
    )
    if not source_assignments:
        raise HTTPException(status_code=404, detail="No active assignments found for split")

    new_display_name = (body.new_display_name or "").strip()
    if not new_display_name:
        new_display_name = f"Split Person {now.strftime('%Y%m%d%H%M%S')}"

    target_person = Person(
        project_id=project_id,
        display_name=new_display_name,
        normalized_name=new_display_name.lower(),
        is_named=True,
        representative_face_detection_id=None,
        sample_count=0,
        confirmed_sample_count=0,
        auto_assigned_count=0,
        review_pending_count=0,
        created_by="human_split",
        updated_at=now,
    )
    db.add(target_person)
    db.flush()

    moved_assignments = 0
    for source_assignment in source_assignments:
        source_assignment.assignment_status = "rejected"
        source_assignment.assignment_source = "human_split"
        source_assignment.is_positive_sample = False
        source_assignment.is_training_candidate = False
        source_assignment.updated_at = now

        target_assignment = _get_assignment(
            db,
            project_id=project_id,
            person_id=target_person.id,
            face_id=source_assignment.face_detection_id,
        )
        if target_assignment is None:
            target_assignment = PersonFaceAssignment(
                project_id=project_id,
                person_id=target_person.id,
                face_detection_id=source_assignment.face_detection_id,
                assignment_status="human_corrected",
                assignment_source="human_split",
                confidence=source_assignment.confidence,
                similarity_score=source_assignment.similarity_score,
                is_positive_sample=True,
                is_training_candidate=True,
                updated_at=now,
            )
            db.add(target_assignment)
        else:
            target_assignment.assignment_status = "human_corrected"
            target_assignment.assignment_source = "human_split"
            target_assignment.is_positive_sample = True
            target_assignment.is_training_candidate = True
            target_assignment.updated_at = now

        _upsert_negative_constraint(
            db,
            project_id=project_id,
            face_id=source_assignment.face_detection_id,
            not_person_id=source_person.id,
            source="human_split",
        )
        _remove_negative_constraint(
            db,
            project_id=project_id,
            face_id=source_assignment.face_detection_id,
            not_person_id=target_person.id,
        )
        if target_person.representative_face_detection_id is None:
            target_person.representative_face_detection_id = source_assignment.face_detection_id
        if source_person.representative_face_detection_id == source_assignment.face_detection_id:
            source_person.representative_face_detection_id = None

        moved_assignments += 1

    source_person.updated_at = now
    target_person.updated_at = now

    db.flush()
    _refresh_person_counters(db, project_id=project_id, person_id=source_person.id)
    _refresh_person_counters(db, project_id=project_id, person_id=target_person.id)
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=source_person.id,
    )
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=target_person.id,
    )

    db.commit()
    db.refresh(source_person)
    db.refresh(target_person)
    logger.info(
        "people.split project_id=%d source_person_id=%d target_person_id=%d moved=%d",
        project_id,
        source_person.id,
        target_person.id,
        moved_assignments,
    )
    return PersonSplitResponse(
        moved_assignments=moved_assignments,
        source_person=PersonSummaryResponse.model_validate(source_person),
        target_person=PersonSummaryResponse.model_validate(target_person),
    )


@router.post(
    "/{project_id}/people/{person_id}/faces/{face_id}/confirm",
    response_model=PersonActionResponse,
)
def confirm_face_assignment(
    project_id: int,
    person_id: int,
    face_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    person = _get_person_or_404(db, project_id, person_id)
    _get_face_or_404(db, project_id, face_id)

    assignment = _get_assignment(
        db,
        project_id=project_id,
        person_id=person_id,
        face_id=face_id,
    )
    now = datetime.now(timezone.utc)
    if assignment is None:
        assignment = PersonFaceAssignment(
            project_id=project_id,
            person_id=person_id,
            face_detection_id=face_id,
            assignment_status="human_confirmed",
            assignment_source="human_label",
            confidence=1.0,
            similarity_score=None,
            is_positive_sample=True,
            is_training_candidate=True,
            updated_at=now,
        )
        db.add(assignment)
    else:
        assignment.assignment_status = "human_confirmed"
        assignment.assignment_source = "human_label"
        assignment.is_positive_sample = True
        assignment.is_training_candidate = True
        assignment.updated_at = now

    # Keep one active assignment per face by rejecting other candidates.
    other_assignments = (
        db.query(PersonFaceAssignment)
        .filter(
            PersonFaceAssignment.project_id == project_id,
            PersonFaceAssignment.face_detection_id == face_id,
            PersonFaceAssignment.person_id != person_id,
            PersonFaceAssignment.assignment_status != "rejected",
        )
        .all()
    )
    touched_person_ids = {person_id}
    for other in other_assignments:
        other.assignment_status = "rejected"
        other.assignment_source = "human_corrected"
        other.is_positive_sample = False
        other.is_training_candidate = False
        other.updated_at = now
        touched_person_ids.add(other.person_id)
        _upsert_negative_constraint(
            db,
            project_id=project_id,
            face_id=face_id,
            not_person_id=other.person_id,
            source="human_corrected",
        )

    _remove_negative_constraint(
        db,
        project_id=project_id,
        face_id=face_id,
        not_person_id=person_id,
    )

    if person.representative_face_detection_id is None:
        person.representative_face_detection_id = face_id

    db.flush()
    for touched_person_id in touched_person_ids:
        _refresh_person_counters(db, project_id=project_id, person_id=touched_person_id)
        rebuild_person_centroid_prototype(
            db,
            project_id=project_id,
            person_id=touched_person_id,
        )

    db.commit()
    db.refresh(person)
    logger.info(
        "people.confirm_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        face_id,
    )
    return PersonActionResponse(person=PersonSummaryResponse.model_validate(person))


@router.post(
    "/{project_id}/people/{person_id}/faces/{face_id}/reject",
    response_model=PersonActionResponse,
)
def reject_face_assignment(
    project_id: int,
    person_id: int,
    face_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    person = _get_person_or_404(db, project_id, person_id)
    _get_face_or_404(db, project_id, face_id)
    assignment = _get_assignment(
        db,
        project_id=project_id,
        person_id=person_id,
        face_id=face_id,
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Face assignment not found for this person")

    assignment.assignment_status = "rejected"
    assignment.assignment_source = "human_rejected"
    assignment.is_positive_sample = False
    assignment.is_training_candidate = False
    assignment.updated_at = datetime.now(timezone.utc)

    _upsert_negative_constraint(
        db,
        project_id=project_id,
        face_id=face_id,
        not_person_id=person_id,
        source="human_rejected",
    )

    if person.representative_face_detection_id == face_id:
        person.representative_face_detection_id = None

    db.flush()
    _refresh_person_counters(db, project_id=project_id, person_id=person_id)
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=person_id,
    )
    db.commit()
    db.refresh(person)
    logger.info(
        "people.reject_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        face_id,
    )
    return PersonActionResponse(person=PersonSummaryResponse.model_validate(person))


@router.post(
    "/{project_id}/people/{person_id}/faces/{face_id}/move",
    response_model=PersonMoveFaceResponse,
)
def move_face_assignment(
    project_id: int,
    person_id: int,
    face_id: int,
    body: PersonFaceMoveRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonMoveFaceResponse:
    source_person = _get_person_or_404(db, project_id, person_id)
    target_person = _get_person_or_404(db, project_id, body.target_person_id)
    if source_person.id == target_person.id:
        raise HTTPException(status_code=422, detail="target_person_id must be different")

    _get_face_or_404(db, project_id, face_id)
    source_assignment = _get_assignment(
        db,
        project_id=project_id,
        person_id=source_person.id,
        face_id=face_id,
    )
    if source_assignment is None:
        raise HTTPException(status_code=404, detail="Face assignment not found for source person")

    now = datetime.now(timezone.utc)
    source_assignment.assignment_status = "rejected"
    source_assignment.assignment_source = "human_move"
    source_assignment.is_positive_sample = False
    source_assignment.is_training_candidate = False
    source_assignment.updated_at = now

    target_assignment = _get_assignment(
        db,
        project_id=project_id,
        person_id=target_person.id,
        face_id=face_id,
    )
    if target_assignment is None:
        target_assignment = PersonFaceAssignment(
            project_id=project_id,
            person_id=target_person.id,
            face_detection_id=face_id,
            assignment_status="human_corrected",
            assignment_source="human_move",
            confidence=1.0,
            similarity_score=None,
            is_positive_sample=True,
            is_training_candidate=True,
            updated_at=now,
        )
        db.add(target_assignment)
    else:
        target_assignment.assignment_status = "human_corrected"
        target_assignment.assignment_source = "human_move"
        target_assignment.is_positive_sample = True
        target_assignment.is_training_candidate = True
        target_assignment.updated_at = now

    _upsert_negative_constraint(
        db,
        project_id=project_id,
        face_id=face_id,
        not_person_id=source_person.id,
        source="human_corrected",
    )
    _remove_negative_constraint(
        db,
        project_id=project_id,
        face_id=face_id,
        not_person_id=target_person.id,
    )

    if source_person.representative_face_detection_id == face_id:
        source_person.representative_face_detection_id = None
    if target_person.representative_face_detection_id is None:
        target_person.representative_face_detection_id = face_id

    db.flush()
    _refresh_person_counters(db, project_id=project_id, person_id=source_person.id)
    _refresh_person_counters(db, project_id=project_id, person_id=target_person.id)
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=source_person.id,
    )
    rebuild_person_centroid_prototype(
        db,
        project_id=project_id,
        person_id=target_person.id,
    )

    db.commit()
    db.refresh(source_person)
    db.refresh(target_person)
    logger.info(
        "people.move_face project_id=%d source_person_id=%d target_person_id=%d face_id=%d",
        project_id,
        source_person.id,
        target_person.id,
        face_id,
    )
    return PersonMoveFaceResponse(
        source_person=PersonSummaryResponse.model_validate(source_person),
        target_person=PersonSummaryResponse.model_validate(target_person),
    )


@router.post(
    "/{project_id}/people/{person_id}/representative-face",
    response_model=PersonActionResponse,
)
def set_representative_face(
    project_id: int,
    person_id: int,
    body: PersonRepresentativeFaceRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    person = _get_person_or_404(db, project_id, person_id)
    _get_face_or_404(db, project_id, body.face_detection_id)
    assignment = _get_assignment(
        db,
        project_id=project_id,
        person_id=person_id,
        face_id=body.face_detection_id,
    )
    if assignment is None or assignment.assignment_status == "rejected":
        raise HTTPException(
            status_code=422,
            detail="Representative face must be an active assignment of this person",
        )
    person.representative_face_detection_id = body.face_detection_id
    person.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(person)
    logger.info(
        "people.set_representative_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        body.face_detection_id,
    )
    return PersonActionResponse(person=PersonSummaryResponse.model_validate(person))


@router.post(
    "/{project_id}/people/{person_id}/review/batch-confirm",
    response_model=PersonBatchActionResponse,
)
def batch_confirm_review_pending(
    project_id: int,
    person_id: int,
    body: PersonBatchReviewRequest,
    request: Request,
    x_operator: Optional[str] = Header(default=None, alias="x-operator"),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonBatchActionResponse:
    request_id, operator = _resolve_batch_audit_fields(
        request,
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )

    def _op() -> PersonBatchActionResponse:
        person = _get_person_or_404(db, project_id, person_id)
        now = datetime.now(timezone.utc)

        face_ids = sorted({int(face_id) for face_id in body.face_detection_ids})
        assignments = (
            db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == "review_pending",
            )
            .all()
        )
        if not assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for this person")

        touched_person_ids = {person_id}
        for assignment in assignments:
            assignment.assignment_status = "human_confirmed"
            assignment.assignment_source = "human_label"
            assignment.is_positive_sample = True
            assignment.is_training_candidate = True
            assignment.updated_at = now

            other_assignments = (
                db.query(PersonFaceAssignment)
                .filter(
                    PersonFaceAssignment.project_id == project_id,
                    PersonFaceAssignment.face_detection_id == assignment.face_detection_id,
                    PersonFaceAssignment.person_id != person_id,
                    PersonFaceAssignment.assignment_status != "rejected",
                )
                .all()
            )
            for other in other_assignments:
                other.assignment_status = "rejected"
                other.assignment_source = "human_corrected"
                other.is_positive_sample = False
                other.is_training_candidate = False
                other.updated_at = now
                touched_person_ids.add(other.person_id)
                _upsert_negative_constraint(
                    db,
                    project_id=project_id,
                    face_id=assignment.face_detection_id,
                    not_person_id=other.person_id,
                    source="human_corrected",
                )
            _remove_negative_constraint(
                db,
                project_id=project_id,
                face_id=assignment.face_detection_id,
                not_person_id=person_id,
            )

            if person.representative_face_detection_id is None:
                person.representative_face_detection_id = assignment.face_detection_id

        db.flush()
        for touched_person_id in touched_person_ids:
            _refresh_person_counters(db, project_id=project_id, person_id=touched_person_id)
            rebuild_person_centroid_prototype(
                db,
                project_id=project_id,
                person_id=touched_person_id,
            )
        db.commit()
        db.refresh(person)

        logger.info(
            "people.batch_confirm_review project_id=%d person_id=%d updated=%d request_id=%s operator=%s",
            project_id,
            person_id,
            len(assignments),
            request_id,
            operator,
        )
        return PersonBatchActionResponse(
            updated=len(assignments),
            person=PersonSummaryResponse.model_validate(person),
        )

    payload, attempts = _execute_batch_with_retry(
        db,
        operation_name="people.batch_confirm_review",
        request_id=request_id,
        operator=operator,
        max_attempts=body.max_retries,
        fn=_op,
    )
    payload.request_id = request_id
    payload.operator = operator
    payload.attempts = attempts
    return payload


@router.post(
    "/{project_id}/people/{person_id}/review/batch-reject",
    response_model=PersonBatchActionResponse,
)
def batch_reject_review_pending(
    project_id: int,
    person_id: int,
    body: PersonBatchReviewRequest,
    request: Request,
    x_operator: Optional[str] = Header(default=None, alias="x-operator"),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonBatchActionResponse:
    request_id, operator = _resolve_batch_audit_fields(
        request,
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )

    def _op() -> PersonBatchActionResponse:
        person = _get_person_or_404(db, project_id, person_id)
        now = datetime.now(timezone.utc)

        face_ids = sorted({int(face_id) for face_id in body.face_detection_ids})
        assignments = (
            db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == person_id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == "review_pending",
            )
            .all()
        )
        if not assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for this person")

        for assignment in assignments:
            assignment.assignment_status = "rejected"
            assignment.assignment_source = "human_rejected"
            assignment.is_positive_sample = False
            assignment.is_training_candidate = False
            assignment.updated_at = now
            _upsert_negative_constraint(
                db,
                project_id=project_id,
                face_id=assignment.face_detection_id,
                not_person_id=person_id,
                source="human_rejected",
            )
            if person.representative_face_detection_id == assignment.face_detection_id:
                person.representative_face_detection_id = None

        db.flush()
        _refresh_person_counters(db, project_id=project_id, person_id=person_id)
        rebuild_person_centroid_prototype(
            db,
            project_id=project_id,
            person_id=person_id,
        )
        db.commit()
        db.refresh(person)

        logger.info(
            "people.batch_reject_review project_id=%d person_id=%d updated=%d request_id=%s operator=%s",
            project_id,
            person_id,
            len(assignments),
            request_id,
            operator,
        )
        return PersonBatchActionResponse(
            updated=len(assignments),
            person=PersonSummaryResponse.model_validate(person),
        )

    payload, attempts = _execute_batch_with_retry(
        db,
        operation_name="people.batch_reject_review",
        request_id=request_id,
        operator=operator,
        max_attempts=body.max_retries,
        fn=_op,
    )
    payload.request_id = request_id
    payload.operator = operator
    payload.attempts = attempts
    return payload


@router.post(
    "/{project_id}/people/{person_id}/review/batch-move",
    response_model=PersonBatchMoveResponse,
)
def batch_move_review_pending(
    project_id: int,
    person_id: int,
    body: PersonBatchMoveRequest,
    request: Request,
    x_operator: Optional[str] = Header(default=None, alias="x-operator"),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonBatchMoveResponse:
    request_id, operator = _resolve_batch_audit_fields(
        request,
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )

    def _op() -> PersonBatchMoveResponse:
        source_person = _get_person_or_404(db, project_id, person_id)
        target_person = _get_person_or_404(db, project_id, body.target_person_id)
        if source_person.id == target_person.id:
            raise HTTPException(status_code=422, detail="target_person_id must be different")

        face_ids = sorted({int(face_id) for face_id in body.face_detection_ids})
        now = datetime.now(timezone.utc)
        source_assignments = (
            db.query(PersonFaceAssignment)
            .filter(
                PersonFaceAssignment.project_id == project_id,
                PersonFaceAssignment.person_id == source_person.id,
                PersonFaceAssignment.face_detection_id.in_(face_ids),
                PersonFaceAssignment.assignment_status == "review_pending",
            )
            .all()
        )
        if not source_assignments:
            raise HTTPException(status_code=404, detail="No review_pending assignments found for source person")

        updated = 0
        for source_assignment in source_assignments:
            source_assignment.assignment_status = "rejected"
            source_assignment.assignment_source = "human_move"
            source_assignment.is_positive_sample = False
            source_assignment.is_training_candidate = False
            source_assignment.updated_at = now

            target_assignment = _get_assignment(
                db,
                project_id=project_id,
                person_id=target_person.id,
                face_id=source_assignment.face_detection_id,
            )
            if target_assignment is None:
                target_assignment = PersonFaceAssignment(
                    project_id=project_id,
                    person_id=target_person.id,
                    face_detection_id=source_assignment.face_detection_id,
                    assignment_status="human_corrected",
                    assignment_source="human_move",
                    confidence=1.0,
                    similarity_score=None,
                    is_positive_sample=True,
                    is_training_candidate=True,
                    updated_at=now,
                )
                db.add(target_assignment)
            else:
                target_assignment.assignment_status = "human_corrected"
                target_assignment.assignment_source = "human_move"
                target_assignment.is_positive_sample = True
                target_assignment.is_training_candidate = True
                target_assignment.updated_at = now

            _upsert_negative_constraint(
                db,
                project_id=project_id,
                face_id=source_assignment.face_detection_id,
                not_person_id=source_person.id,
                source="human_corrected",
            )
            _remove_negative_constraint(
                db,
                project_id=project_id,
                face_id=source_assignment.face_detection_id,
                not_person_id=target_person.id,
            )

            if source_person.representative_face_detection_id == source_assignment.face_detection_id:
                source_person.representative_face_detection_id = None
            if target_person.representative_face_detection_id is None:
                target_person.representative_face_detection_id = source_assignment.face_detection_id
            updated += 1

        db.flush()
        _refresh_person_counters(db, project_id=project_id, person_id=source_person.id)
        _refresh_person_counters(db, project_id=project_id, person_id=target_person.id)
        rebuild_person_centroid_prototype(
            db,
            project_id=project_id,
            person_id=source_person.id,
        )
        rebuild_person_centroid_prototype(
            db,
            project_id=project_id,
            person_id=target_person.id,
        )
        db.commit()
        db.refresh(source_person)
        db.refresh(target_person)

        logger.info(
            "people.batch_move_review project_id=%d source_person_id=%d target_person_id=%d updated=%d request_id=%s operator=%s",
            project_id,
            source_person.id,
            target_person.id,
            updated,
            request_id,
            operator,
        )
        return PersonBatchMoveResponse(
            updated=updated,
            source_person=PersonSummaryResponse.model_validate(source_person),
            target_person=PersonSummaryResponse.model_validate(target_person),
        )

    payload, attempts = _execute_batch_with_retry(
        db,
        operation_name="people.batch_move_review",
        request_id=request_id,
        operator=operator,
        max_attempts=body.max_retries,
        fn=_op,
    )
    payload.request_id = request_id
    payload.operator = operator
    payload.attempts = attempts
    return payload
