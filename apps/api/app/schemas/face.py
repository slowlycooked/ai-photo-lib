from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectFaceSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    face_recognition_enabled: bool
    face_provider: str
    face_detector_model: str
    face_embedding_model: str
    face_runtime: str
    store_face_crops: bool
    face_crop_storage: str
    auto_accept_threshold: float
    review_threshold: float
    cluster_threshold: float
    min_face_size: int
    min_detection_confidence: float
    min_quality_for_prototype: float
    max_positive_samples_per_person: int
    allow_auto_assignment: bool
    require_human_confirmation_for_new_person: bool
    enable_negative_constraints: bool
    enable_person_cannot_links: bool
    created_at: datetime
    updated_at: datetime


class ProjectFaceSettingsUpdate(BaseModel):
    face_recognition_enabled: Optional[bool] = None
    face_provider: Optional[str] = None
    face_detector_model: Optional[str] = None
    face_embedding_model: Optional[str] = None
    face_runtime: Optional[str] = None
    store_face_crops: Optional[bool] = None
    face_crop_storage: Optional[str] = None
    auto_accept_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    review_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    cluster_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_face_size: Optional[int] = Field(None, ge=1, le=4096)
    min_detection_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    min_quality_for_prototype: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_positive_samples_per_person: Optional[int] = Field(None, ge=1, le=10000)
    allow_auto_assignment: Optional[bool] = None
    require_human_confirmation_for_new_person: Optional[bool] = None
    enable_negative_constraints: Optional[bool] = None
    enable_person_cannot_links: Optional[bool] = None


class FaceEmbeddingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    face_detection_id: int
    model_provider: Optional[str] = None
    model_name: str
    model_version: str
    embedding_dim: int
    embedding_hash: Optional[str] = None
    embedded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FaceDetectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    photo_id: int
    bbox_x: int
    bbox_y: int
    bbox_w: int
    bbox_h: int
    detection_confidence: Optional[float] = None
    face_quality_score: Optional[float] = None
    face_crop_path: Optional[str] = None
    face_crop_hash: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    detected_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FaceDetectionDetailResponse(FaceDetectionResponse):
    embeddings: list[FaceEmbeddingResponse] = Field(default_factory=list)


class FaceDetectionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[FaceDetectionResponse]


class FaceScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    photo_id: int
    provider: str
    detector_model: str
    embedding_model: str
    faces_detected: int
    detections_created: int
    detections_updated: int
    embeddings_created: int
    embeddings_updated: int
    auto_assigned: int
    review_pending: int
    failures: int
    message: str
    scan_source: str = "face_work_image"
    scan_quality_degraded: bool = False


class FaceScanProjectStartRequest(BaseModel):
    scope: Literal["missing", "failed", "stale", "all", "selected"] = "missing"
    photo_ids: list[int] = Field(default_factory=list)
    force: bool = False
    dry_run: bool = False


class FaceScanProjectStartResponse(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    task_created: bool = False
    task_status: Optional[str] = None
    created_jobs: int
    skipped_active_jobs: int
    scope: Literal["missing", "failed", "stale", "all", "selected"] = "missing"
    total_photos: int = 0
    candidate_count: int = 0
    skipped_already_scanned: int = 0
    skipped_other_project: int = 0
    stale_count: int = 0
    failed_count: int = 0
    dry_run: bool = False
    message: str


class FaceScanProjectStatusResponse(BaseModel):
    queued: int
    running: int
    success: int
    failed: int
    total: int
    task_id: Optional[int] = None
    task_status: Optional[str] = None


class FaceClusterUnknownRequest(BaseModel):
    max_faces: int = Field(500, ge=1, le=5000)


class FaceClusterUnknownStatusResponse(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    status: str
    running: bool
    max_faces: int = 500
    clusters_created: int = 0
    persons_created: int = 0
    faces_clustered: int = 0
    assignments_created: int = 0
    errors: int = 0
    recent_errors: list[str] = Field(default_factory=list)
    message: str


class FaceClusterUnknownResponse(BaseModel):
    message: str
    status: FaceClusterUnknownStatusResponse


class FaceRematchUnknownRequest(BaseModel):
    max_faces: int = Field(1000, ge=1, le=10000)
    scope: Literal["unknown", "person", "time_range", "project"] = "unknown"
    person_id: Optional[int] = Field(default=None, ge=1)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class FaceRematchUnknownStatusResponse(BaseModel):
    project_id: int
    task_id: Optional[int] = None
    status: str
    running: bool
    max_faces: int = 1000
    scope: Literal["unknown", "person", "time_range", "project"] = "unknown"
    person_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    faces_considered: int = 0
    matched_faces: int = 0
    auto_assigned: int = 0
    review_pending: int = 0
    errors: int = 0
    recent_errors: list[str] = Field(default_factory=list)
    message: str


class FaceRematchUnknownResponse(BaseModel):
    message: str
    status: FaceRematchUnknownStatusResponse


class PersonSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    display_name: str
    normalized_name: Optional[str] = None
    is_named: bool
    representative_face_detection_id: Optional[int] = None
    sample_count: int
    confirmed_sample_count: int
    auto_assigned_count: int
    review_pending_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class PersonListResponse(BaseModel):
    total: int
    items: list[PersonSummaryResponse]


class PersonFaceAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    person_id: int
    face_detection_id: int
    assignment_status: str
    assignment_source: str
    confidence: Optional[float] = None
    similarity_score: Optional[float] = None
    is_positive_sample: bool
    is_training_candidate: bool
    created_at: datetime
    updated_at: datetime
    explanation: Optional["PersonMatchExplanationResponse"] = None
    face_detection: FaceDetectionResponse


class PersonMatchExplanationResponse(BaseModel):
    similarity: Optional[float] = None
    source: str
    is_auto: bool
    is_human_confirmed: bool
    negative_constraint_affected: bool
    negative_constraint_count: int = 0


class PersonDetailResponse(PersonSummaryResponse):
    assignments: list[PersonFaceAssignmentResponse] = Field(default_factory=list)


class PersonRenameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


class PersonCreateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=200)
    is_named: bool = True


class PersonMergeRequest(BaseModel):
    target_person_id: int = Field(ge=1)


class PersonSplitRequest(BaseModel):
    face_detection_ids: list[int] = Field(min_length=1, max_length=500)
    new_display_name: Optional[str] = Field(default=None, max_length=200)


class PersonFaceMoveRequest(BaseModel):
    target_person_id: int = Field(ge=1)


class PersonRepresentativeFaceRequest(BaseModel):
    face_detection_id: int = Field(ge=1)


class PersonActionResponse(BaseModel):
    person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None


class PersonMoveFaceResponse(BaseModel):
    source_person: PersonSummaryResponse
    target_person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None


class PersonMergeResponse(BaseModel):
    moved_assignments: int
    source_person: PersonSummaryResponse
    target_person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None


class PersonSplitResponse(BaseModel):
    moved_assignments: int
    source_person: PersonSummaryResponse
    target_person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None


class PersonReviewListResponse(BaseModel):
    total: int
    items: list[PersonFaceAssignmentResponse]


class PersonBatchReviewRequest(BaseModel):
    face_detection_ids: list[int] = Field(min_length=1, max_length=500)
    request_id: Optional[str] = Field(default=None, max_length=128)
    operator: Optional[str] = Field(default=None, max_length=128)
    max_retries: int = Field(default=1, ge=1, le=5)


class PersonBatchMoveRequest(PersonBatchReviewRequest):
    target_person_id: int = Field(ge=1)


class PersonBatchActionResponse(BaseModel):
    updated: int
    person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None
    request_id: Optional[str] = None
    operator: Optional[str] = None
    attempts: int = 1


class PersonBatchMoveResponse(BaseModel):
    updated: int
    source_person: PersonSummaryResponse
    target_person: PersonSummaryResponse
    feedback_effects: Optional["PersonFeedbackEffectsResponse"] = None
    request_id: Optional[str] = None
    operator: Optional[str] = None
    attempts: int = 1


class PersonFeedbackEffectsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prototype_rebuilt: bool
    rebuilt_person_ids: list[int] = Field(default_factory=list)
    unknown_rematch_requested: bool = False
    unknown_rematch_scope: Optional[Literal["unknown", "person", "time_range", "project"]] = None
    unknown_rematch_person_id: Optional[int] = None
    unknown_rematch_task_id: Optional[int] = None
    unknown_rematch_task_created: bool = False
