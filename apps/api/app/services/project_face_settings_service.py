"""Service for managing per-project face recognition settings."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..config import settings as global_settings
from ..models.face import ProjectFaceSettings

logger = logging.getLogger(__name__)


def get_project_face_settings(
    db: Session, project_id: int
) -> ProjectFaceSettings | None:
    return (
        db.query(ProjectFaceSettings)
        .filter(ProjectFaceSettings.project_id == project_id)
        .first()
    )


def get_or_create_project_face_settings(
    db: Session, project_id: int
) -> ProjectFaceSettings:
    row = get_project_face_settings(db, project_id)
    if row is not None:
        return row

    row = ProjectFaceSettings(
        project_id=project_id,
        face_recognition_enabled=global_settings.face_recognition_enabled,
        face_provider=global_settings.face_provider,
        face_detector_model=global_settings.face_detector_model,
        face_embedding_model=global_settings.face_embedding_model,
        face_runtime=global_settings.face_runtime,
        store_face_crops=global_settings.store_face_crops,
        face_crop_storage=global_settings.face_crop_storage,
        auto_accept_threshold=global_settings.face_auto_accept_threshold,
        review_threshold=global_settings.face_review_threshold,
        cluster_threshold=global_settings.face_cluster_threshold,
        min_face_size=global_settings.face_min_face_size,
        min_detection_confidence=global_settings.face_min_detection_confidence,
        min_quality_for_prototype=global_settings.face_min_quality_for_prototype,
        max_positive_samples_per_person=global_settings.face_max_positive_samples_per_person,
        allow_auto_assignment=global_settings.face_allow_auto_assignment,
        require_human_confirmation_for_new_person=(
            global_settings.face_require_human_confirmation_for_new_person
        ),
        enable_negative_constraints=global_settings.face_enable_negative_constraints,
        enable_person_cannot_links=global_settings.face_enable_person_cannot_links,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Created default project_face_settings for project_id=%s", project_id)
    return row


def update_project_face_settings(
    db: Session,
    project_id: int,
    updates: dict,
) -> ProjectFaceSettings:
    row = get_or_create_project_face_settings(db, project_id)

    allowed_fields = {
        "face_recognition_enabled",
        "face_provider",
        "face_detector_model",
        "face_embedding_model",
        "face_runtime",
        "store_face_crops",
        "face_crop_storage",
        "auto_accept_threshold",
        "review_threshold",
        "cluster_threshold",
        "min_face_size",
        "min_detection_confidence",
        "min_quality_for_prototype",
        "max_positive_samples_per_person",
        "allow_auto_assignment",
        "require_human_confirmation_for_new_person",
        "enable_negative_constraints",
        "enable_person_cannot_links",
    }
    for key, value in updates.items():
        if key not in allowed_fields:
            raise ValueError(f"Unknown face settings field: {key!r}")
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return row


def reset_project_face_settings(
    db: Session, project_id: int
) -> ProjectFaceSettings:
    row = get_project_face_settings(db, project_id)
    if row is not None:
        db.delete(row)
        db.commit()
        logger.info(
            "Deleted project_face_settings for project_id=%s (reset to defaults)",
            project_id,
        )
    return get_or_create_project_face_settings(db, project_id)
