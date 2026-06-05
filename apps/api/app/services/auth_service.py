from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..schemas.user import CurrentUser

SESSION_COOKIE_NAME = "ai_photo_session"


def auth_password_configured() -> bool:
    return bool(settings.auth_password)


def verify_credentials(username: str, password: str) -> bool:
    if not settings.auth_password:
        return False
    return secrets.compare_digest(username, settings.auth_username) and secrets.compare_digest(
        password,
        settings.auth_password,
    )


def create_session_cookie(
    username: str,
    now: datetime | None = None,
    *,
    user_id: int | None = None,
    role: str = "admin",
    display_name: str | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.auth_session_timeout_minutes)
    payload = {
        "sub": username,
        "uid": user_id,
        "role": role,
        "name": display_name,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_token = _b64encode(payload_bytes)
    signature = _sign(payload_token)
    return f"{payload_token}.{signature}"


def verify_session_cookie(value: str | None, now: datetime | None = None) -> dict[str, Any] | None:
    if not value or "." not in value:
        return None

    payload_token, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload_token), signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_token))
    except (ValueError, json.JSONDecodeError):
        return None

    username = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(username, str) or not isinstance(expires_at, int):
        return None

    current = now or datetime.now(timezone.utc)
    if expires_at <= int(current.timestamp()):
        return None

    return payload


def current_user_from_session(session: dict[str, Any]) -> CurrentUser:
    role = str(session.get("role") or "admin")
    if role not in {"admin", "project_manager", "viewer"}:
        role = "viewer"
    uid = session.get("uid")
    return CurrentUser(
        id=uid if isinstance(uid, int) else None,
        username=str(session["sub"]),
        display_name=session.get("name") if isinstance(session.get("name"), str) else None,
        role=role,  # type: ignore[arg-type]
        bootstrap=uid is None and role == "admin",
    )


def _sign(payload_token: str) -> str:
    return hmac.new(_session_secret(), payload_token.encode("utf-8"), hashlib.sha256).hexdigest()


def _session_secret() -> bytes:
    secret = settings.auth_session_secret or settings.auth_password
    return secret.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}").decode("utf-8")
