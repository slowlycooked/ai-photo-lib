from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..api.deps import get_current_user, require_admin
from ..database import get_db
from ..schemas.user import (
    AIServiceProfileCreate,
    AIServiceProfileListResponse,
    AIServiceProfileUpdate,
    CurrentUser,
)
from ..services.user_service import AIServiceProfileService, UserNotFoundError

router = APIRouter(prefix="/settings/ai-profiles", tags=["ai-service-profiles"])


@router.get("", response_model=AIServiceProfileListResponse)
def list_ai_profiles(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = AIServiceProfileService(db).list_profiles(admin=current_user.role == "admin")
    return AIServiceProfileListResponse(total=len(rows), items=rows)


@router.post("", response_model=AIServiceProfileListResponse, status_code=201)
def create_ai_profile(
    body: AIServiceProfileCreate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    AIServiceProfileService(db).create_profile(body)
    rows = AIServiceProfileService(db).list_profiles(admin=True)
    return AIServiceProfileListResponse(total=len(rows), items=rows)


@router.post("/import-env", response_model=AIServiceProfileListResponse)
def import_ai_profiles_from_env(
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    AIServiceProfileService(db).import_from_environment()
    rows = AIServiceProfileService(db).list_profiles(admin=True)
    return AIServiceProfileListResponse(total=len(rows), items=rows)


@router.put("/{profile_id}", response_model=AIServiceProfileListResponse)
def update_ai_profile(
    profile_id: int,
    body: AIServiceProfileUpdate,
    _: object = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        AIServiceProfileService(db).update_profile(profile_id, body)
    except UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = AIServiceProfileService(db).list_profiles(admin=True)
    return AIServiceProfileListResponse(total=len(rows), items=rows)
