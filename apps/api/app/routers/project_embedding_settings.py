"""Router for per-project embedding configuration.

Endpoints:
  GET  /projects/{project_id}/embedding-settings
  PUT  /projects/{project_id}/embedding-settings
  POST /projects/{project_id}/embedding-settings/test
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.deps import require_project
from ..config import settings
from ..database import get_db
from ..models.project import Project
from ..services.embedding_client import EmbeddingRequestError, embed_text
from ..services.project_embedding_settings_service import (
    get_or_create_project_embedding_settings,
    update_project_embedding_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects-embedding-settings"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ProjectEmbeddingSettingsResponse(BaseModel):
    id: int
    project_id: int
    provider: str
    endpoint_url: str
    # api_key intentionally omitted from response for security
    model_name: str
    embedding_dimension: int
    batch_size: int
    timeout_seconds: int
    input_prefix_query: Optional[str]
    input_prefix_document: Optional[str]
    enabled: bool
    search_content_vector_weight: float
    search_tag_vector_weight: float
    search_caption_vector_weight: float
    search_ocr_vector_weight: float

    class Config:
        from_attributes = True


class ProjectEmbeddingSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    endpoint_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    embedding_dimension: Optional[int] = None
    batch_size: Optional[int] = None
    timeout_seconds: Optional[int] = None
    input_prefix_query: Optional[str] = None
    input_prefix_document: Optional[str] = None
    enabled: Optional[bool] = None
    search_content_vector_weight: Optional[float] = None
    search_tag_vector_weight: Optional[float] = None
    search_caption_vector_weight: Optional[float] = None
    search_ocr_vector_weight: Optional[float] = None


class EmbeddingTestRequest(BaseModel):
    text: str


class EmbeddingTestResponse(BaseModel):
    success: bool
    model_name: str
    embedding_dimension: int
    sample: list[float]
    duration_ms: float
    error: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/{project_id}/embedding-settings",
    response_model=ProjectEmbeddingSettingsResponse,
)
def get_embedding_settings(
    project_id: int,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Return the embedding configuration for a project.

    Creates a default row from global config if none exists.
    """
    try:
        row = get_or_create_project_embedding_settings(db, project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return row


@router.put(
    "/{project_id}/embedding-settings",
    response_model=ProjectEmbeddingSettingsResponse,
)
def put_embedding_settings(
    project_id: int,
    body: ProjectEmbeddingSettingsUpdate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Update embedding configuration for a project."""
    try:
        row = update_project_embedding_settings(
            db,
            project_id,
            body.model_dump(exclude_none=True),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "Embedding settings updated. project_id=%s model=%s endpoint=%s",
        project_id,
        row.model_name,
        row.endpoint_url,
    )
    return row


@router.post(
    "/{project_id}/embedding-settings/test",
    response_model=EmbeddingTestResponse,
)
def test_embedding_settings(
    project_id: int,
    body: EmbeddingTestRequest,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    """Send a test text to the configured embedding endpoint.

    Returns the first 3–5 elements of the resulting vector along with the
    embedding model name, dimension, and latency.
    """
    try:
        row = get_or_create_project_embedding_settings(db, project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    expected_dim = row.embedding_dimension

    start = time.monotonic()
    try:
        vector = embed_text(
            body.text.strip() or "test",
            endpoint_url=row.endpoint_url,
            api_key=row.api_key or settings.embedding_api_key or settings.openai_api_key,
            model=row.model_name,
            timeout_seconds=row.timeout_seconds,
            expected_dim=expected_dim,
        )
    except EmbeddingRequestError as exc:
        duration_ms = (time.monotonic() - start) * 1000
        logger.warning(
            "Embedding test failed. project_id=%s model=%s error=%s",
            project_id,
            row.model_name,
            exc,
        )
        return EmbeddingTestResponse(
            success=False,
            model_name=row.model_name,
            embedding_dimension=expected_dim,
            sample=[],
            duration_ms=round(duration_ms, 1),
            error=str(exc),
        )

    duration_ms = (time.monotonic() - start) * 1000
    actual_dim = len(vector)

    if actual_dim != expected_dim:
        return EmbeddingTestResponse(
            success=False,
            model_name=row.model_name,
            embedding_dimension=actual_dim,
            sample=vector[:5],
            duration_ms=round(duration_ms, 1),
            error=(
                f"Embedding dimension mismatch: "
                f"expected_dim={expected_dim}, actual_dim={actual_dim}. "
                "Update embedding_dimension in settings to match the model."
            ),
        )

    logger.info(
        "Embedding test succeeded. project_id=%s model=%s dimension=%s duration_ms=%.1f",
        project_id,
        row.model_name,
        actual_dim,
        duration_ms,
    )
    return EmbeddingTestResponse(
        success=True,
        model_name=row.model_name,
        embedding_dimension=actual_dim,
        sample=[round(v, 6) for v in vector[:5]],
        duration_ms=round(duration_ms, 1),
    )
