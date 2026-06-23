from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..api.deps import require_admin
from ..schemas.debug_config import DebugConfig, DebugConfigUpdate, DebugSettingsResponse, build_default_debug_config
from ..services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)
from ..database import get_db
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    config_scope: str
    project_authoritative: bool
    note: str
    photo_library_path: str
    host_photo_library_path: str
    thumbnail_path: str
    thumbnail_size: int
    openai_base_url: str
    openai_model: str
    openai_vision_model: str
    ai_max_retries: int
    ai_worker_concurrency: int


@router.get("", response_model=SettingsResponse)
def get_settings(_: object = Depends(require_admin)):
    return SettingsResponse(
        config_scope="global",
        project_authoritative=False,
        note=(
            "Global diagnostics only. Runtime project behavior should be configured via "
            "/projects/{project_id}/... settings endpoints."
        ),
        photo_library_path=settings.photo_library_path,
        host_photo_library_path=settings.host_photo_library_path,
        thumbnail_path=settings.thumbnail_path,
        thumbnail_size=settings.thumbnail_size,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        openai_vision_model=settings.openai_vision_model,
        ai_max_retries=settings.ai_max_retries,
        ai_worker_concurrency=settings.ai_worker_concurrency,
    )


@router.get("/debug", response_model=DebugSettingsResponse)
def get_debug_config(
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        config = RuntimeSettingsService.get_debug_config(db)
    except RuntimeSettingsStorageUnavailableError as exc:
        logger.error(
            "Debug config storage unavailable (endpoint=GET /settings/debug). Returning default config. Cause: %s",
            exc,
        )
        config = DebugConfig(**build_default_debug_config().model_dump())
    return DebugSettingsResponse(**config.model_dump())


@router.put("/debug", response_model=DebugSettingsResponse)
def update_debug_config(
    cfg: DebugConfigUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        saved = RuntimeSettingsService.set_debug_config(db, cfg)
    except RuntimeSettingsStorageUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    RuntimeSettingsService.clear_cache()
    return DebugSettingsResponse(**saved.model_dump())
from ..api.deps import require_admin
