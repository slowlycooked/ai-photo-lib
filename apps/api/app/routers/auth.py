from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..api.deps import get_current_user
from ..database import get_db
from ..schemas.user import AuthSessionResponse, CurrentUser
from ..services.auth_service import (
    SESSION_COOKIE_NAME,
    auth_password_configured,
    create_session_cookie,
    verify_credentials,
)
from ..services.user_service import UserService, capabilities_for_role

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    if not auth_password_configured():
        raise HTTPException(status_code=503, detail="AUTH_PASSWORD is not configured")

    db_user = None
    try:
        db_user = UserService(db).authenticate(payload.username, payload.password)
    except SQLAlchemyError:
        db.rollback()

    if db_user is not None:
        role = db_user.role
        user_id = db_user.id
        display_name = db_user.display_name
        username = db_user.username
    elif verify_credentials(payload.username, payload.password):
        role = "admin"
        user_id = None
        display_name = "Bootstrap Admin"
        username = payload.username
    else:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(
            username,
            user_id=user_id,
            role=role,
            display_name=display_name,
        ),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_timeout_minutes * 60,
        path="/",
    )
    return AuthSessionResponse(
        user_id=user_id,
        username=username,
        display_name=display_name,
        role=role,
        capabilities=capabilities_for_role(role),
        sessionTimeoutMinutes=settings.auth_session_timeout_minutes,
    )


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax")


@router.get("/me", response_model=AuthSessionResponse)
def me(current_user: CurrentUser = Depends(get_current_user)):
    return AuthSessionResponse(
        user_id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        role=current_user.role,
        capabilities=capabilities_for_role(current_user.role),
        sessionTimeoutMinutes=settings.auth_session_timeout_minutes,
    )
