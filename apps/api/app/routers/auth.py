from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Response

from ..config import settings
from ..services.auth_service import (
    SESSION_COOKIE_NAME,
    auth_password_configured,
    create_session_cookie,
    verify_credentials,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    if not auth_password_configured():
        raise HTTPException(status_code=503, detail="AUTH_PASSWORD is not configured")
    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(payload.username),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_timeout_minutes * 60,
        path="/",
    )
    return {
        "username": payload.username,
        "sessionTimeoutMinutes": settings.auth_session_timeout_minutes,
    }


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax")


@router.get("/me")
def me():
    return {
        "username": settings.auth_username,
        "sessionTimeoutMinutes": settings.auth_session_timeout_minutes,
    }
