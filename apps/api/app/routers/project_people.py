from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_project
from ..logging_config import request_id_ctx
from ..models.project import Project
from ..schemas.face import (
    PersonActionResponse,
    PersonBatchActionResponse,
    PersonBatchMoveRequest,
    PersonBatchMoveResponse,
    PersonBatchReviewRequest,
    PersonCreateRequest,
    PersonDetailResponse,
    PersonFaceMoveRequest,
    PersonFeedbackEffectsResponse,
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
from ..services.people_assignment_mutation_service import PeopleAssignmentMutationService
from ..services.people_audit_service import PeopleAuditService
from ..services.people_batch_review_service import PeopleBatchReviewService
from ..services.people_lifecycle_mutation_service import PeopleLifecycleMutationService
from ..services.people_query_service import PeopleQueryService

router = APIRouter(prefix="/projects", tags=["project-people"])
logger = logging.getLogger(__name__)


@router.get("/{project_id}/people/review", response_model=PersonReviewListResponse)
def list_project_review_pending(
    project_id: int,
    person_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonReviewListResponse:
    return PeopleQueryService(db).list_review_pending(
        project_id=project_id,
        person_id=person_id,
        limit=limit,
        offset=offset,
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
    return PeopleQueryService(db).list_people(
        project_id=project_id,
        include_unnamed=include_unnamed,
        is_named=is_named,
        has_review_pending=has_review_pending,
        min_sample_count=min_sample_count,
        min_auto_assigned_count=min_auto_assigned_count,
        q=q,
        limit=limit,
    )


@router.post("/{project_id}/people", response_model=PersonActionResponse)
def create_project_person(
    project_id: int,
    body: PersonCreateRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    service = PeopleLifecycleMutationService(db)
    person = service.create_person(
        project_id=project_id,
        display_name=body.display_name,
        is_named=body.is_named,
    )
    logger.info(
        "people.create project_id=%d person_id=%d display_name=%s",
        project_id,
        person.id,
        person.display_name,
    )
    return PersonActionResponse(
        person=PersonSummaryResponse.model_validate(person),
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
    )


@router.get("/{project_id}/people/{person_id}", response_model=PersonDetailResponse)
def get_project_person(
    project_id: int,
    person_id: int,
    assignment_limit: int = Query(120, ge=1, le=500),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonDetailResponse:
    return PeopleQueryService(db).get_person_detail(
        project_id=project_id,
        person_id=person_id,
        assignment_limit=assignment_limit,
    )


@router.patch("/{project_id}/people/{person_id}", response_model=PersonActionResponse)
def rename_project_person(
    project_id: int,
    person_id: int,
    body: PersonRenameRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> PersonActionResponse:
    service = PeopleLifecycleMutationService(db)
    person = service.rename_person(
        project_id=project_id,
        person_id=person_id,
        display_name=body.display_name,
    )
    logger.info(
        "people.rename project_id=%d person_id=%d display_name=%s",
        project_id,
        person_id,
        person.display_name,
    )
    return PersonActionResponse(
        person=PersonSummaryResponse.model_validate(person),
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
    )


@router.delete("/{project_id}/people/{person_id}", response_model=dict)
def delete_project_person(
    project_id: int,
    person_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
) -> dict:
    service = PeopleLifecycleMutationService(db)
    service.delete_person(project_id=project_id, person_id=person_id)
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
    service = PeopleLifecycleMutationService(db)
    source_person, target_person, moved_assignments = service.merge_people(
        project_id=project_id,
        source_person_id=source_person_id,
        target_person_id=body.target_person_id,
    )
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
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
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
    service = PeopleLifecycleMutationService(db)
    source_person, target_person, moved_assignments = service.split_person(
        project_id=project_id,
        person_id=person_id,
        face_detection_ids=body.face_detection_ids,
        new_display_name=body.new_display_name,
    )
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
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
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
    service = PeopleAssignmentMutationService(db)
    person = service.confirm_assignment(
        project_id=project_id,
        person_id=person_id,
        face_id=face_id,
    )
    logger.info(
        "people.confirm_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        face_id,
    )
    return PersonActionResponse(
        person=PersonSummaryResponse.model_validate(person),
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
    )


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
    service = PeopleAssignmentMutationService(db)
    person = service.exclude_assignment(
        project_id=project_id,
        person_id=person_id,
        face_id=face_id,
    )
    logger.info(
        "people.reject_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        face_id,
    )
    return PersonActionResponse(
        person=PersonSummaryResponse.model_validate(person),
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
    )


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
    service = PeopleAssignmentMutationService(db)
    source_person, target_person = service.move_face(
        project_id=project_id,
        source_person_id=person_id,
        face_id=face_id,
        target_person_id=body.target_person_id,
    )
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
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
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
    service = PeopleAssignmentMutationService(db)
    person = service.set_cover_face(
        project_id=project_id,
        person_id=person_id,
        face_id=body.face_detection_id,
    )
    logger.info(
        "people.set_representative_face project_id=%d person_id=%d face_id=%d",
        project_id,
        person_id,
        body.face_detection_id,
    )
    return PersonActionResponse(
        person=PersonSummaryResponse.model_validate(person),
        feedback_effects=PersonFeedbackEffectsResponse.model_validate(service.get_feedback_effects()),
    )


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
    audit = PeopleAuditService.resolve_batch_fields(
        headers=request.headers,
        context_request_id=request_id_ctx.get(),
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )
    return PeopleBatchReviewService(db).batch_confirm_review_pending(
        project_id=project_id,
        person_id=person_id,
        face_detection_ids=body.face_detection_ids,
        audit=audit,
        max_attempts=body.max_retries,
    )


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
    audit = PeopleAuditService.resolve_batch_fields(
        headers=request.headers,
        context_request_id=request_id_ctx.get(),
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )
    return PeopleBatchReviewService(db).batch_reject_review_pending(
        project_id=project_id,
        person_id=person_id,
        face_detection_ids=body.face_detection_ids,
        audit=audit,
        max_attempts=body.max_retries,
    )


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
    audit = PeopleAuditService.resolve_batch_fields(
        headers=request.headers,
        context_request_id=request_id_ctx.get(),
        body_request_id=body.request_id,
        body_operator=body.operator,
        header_operator=x_operator,
    )
    return PeopleBatchReviewService(db).batch_move_review_pending(
        project_id=project_id,
        source_person_id=person_id,
        target_person_id=body.target_person_id,
        face_detection_ids=body.face_detection_ids,
        audit=audit,
        max_attempts=body.max_retries,
    )
