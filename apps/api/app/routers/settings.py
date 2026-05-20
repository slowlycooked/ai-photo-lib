from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..schemas.debug_config import DebugConfig
from ..services.runtime_settings_service import RuntimeSettingsService
from ..database import get_db

from ..config import settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    photo_library_path: str
    host_photo_library_path: str
    thumbnail_path: str
    thumbnail_size: int
    openai_base_url: str
    openai_model: str
    openai_vision_model: str
    ai_worker_concurrency: int
    ai_max_retries: int


@router.get("", response_model=SettingsResponse)
def get_settings():
    return SettingsResponse(
        photo_library_path=settings.photo_library_path,
        host_photo_library_path=settings.host_photo_library_path,
        thumbnail_path=settings.thumbnail_path,
        thumbnail_size=settings.thumbnail_size,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        openai_vision_model=settings.openai_vision_model,
        ai_worker_concurrency=settings.ai_worker_concurrency,
        ai_max_retries=settings.ai_max_retries,
    )


@router.get("/debug", response_model=DebugConfig)
def get_debug_config(db: Session = Depends(get_db)):
    config = RuntimeSettingsService.get_debug_config(db)
    return config

@router.put("/debug", response_model=DebugConfig)
def update_debug_config(cfg: DebugConfig, db: Session = Depends(get_db)):
    RuntimeSettingsService.set_debug_config(db, cfg)
    RuntimeSettingsService.clear_cache()
    return cfg
