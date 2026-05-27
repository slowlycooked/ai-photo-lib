from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .._version import APP_VERSION
from ..config import settings
from ..database import get_db

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check():
    return {"status": "ok", "version": APP_VERSION, "service": "ai-photo-lib"}


@router.get("/health/system")
def system_health_check(db: Session = Depends(get_db)):
    checks = [
        _database_check(db),
        _pgvector_check(db),
        _alembic_check(db),
        _path_check("thumbnail_path writable", settings.thumbnail_path, writable=True),
        _path_check("photo_library_path readable", settings.photo_library_path, readable=True),
        _configured_check("llama vision endpoint configured", settings.openai_base_url),
        _configured_check("embedding endpoint configured", settings.embedding_base_url),
        _file_check("YuNet model path", settings.face_detector_model_path),
        _file_check("SFace model path", settings.face_embedding_model_path),
        _auth_check(),
    ]
    overall = "ok"
    if any(check["status"] == "fail" for check in checks):
        overall = "fail"
    elif any(check["status"] == "warn" for check in checks):
        overall = "warn"
    return {
        "status": overall,
        "version": APP_VERSION,
        "checks": checks,
    }


def _check(name: str, status: str, message: str = "") -> dict:
    return {"name": name, "status": status, "message": message}


def _database_check(db: Session) -> dict:
    try:
        db.execute(sa.text("SELECT 1")).scalar()
    except Exception as exc:  # noqa: BLE001
        return _check("database", "fail", str(exc))
    return _check("database", "ok", "connected")


def _pgvector_check(db: Session) -> dict:
    if db.get_bind().dialect.name != "postgresql":
        return _check("pgvector", "warn", "not required for sqlite")
    try:
        found = db.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).first()
    except Exception as exc:  # noqa: BLE001
        return _check("pgvector", "fail", str(exc))
    return _check("pgvector", "ok" if found else "fail", "installed" if found else "missing")


def _alembic_check(db: Session) -> dict:
    try:
        version = db.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        return _check("alembic head", "warn", str(exc))
    return _check("alembic head", "ok" if version else "warn", str(version or "unknown"))


def _path_check(name: str, raw_path: str, *, readable: bool = False, writable: bool = False) -> dict:
    path = Path(raw_path)
    if not raw_path:
        return _check(name, "fail", "not configured")
    if readable and not path.exists():
        return _check(name, "fail", f"{raw_path} does not exist")
    if readable and not path.is_dir():
        return _check(name, "warn", f"{raw_path} is not a directory")
    if writable:
        target = path if path.exists() else path.parent
        if not target.exists():
            return _check(name, "fail", f"{target} does not exist")
        probe = target / ".ai-photo-lib-healthcheck"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            return _check(name, "fail", str(exc))
    return _check(name, "ok", raw_path)


def _configured_check(name: str, value: str) -> dict:
    return _check(name, "ok" if value else "warn", "configured" if value else "not configured")


def _file_check(name: str, raw_path: str) -> dict:
    if not raw_path:
        return _check(name, "warn", "not configured")
    path = Path(raw_path)
    return _check(name, "ok" if path.exists() else "fail", raw_path)


def _auth_check() -> dict:
    if not settings.auth_enabled:
        return _check("auth configured", "warn", "auth disabled")
    missing = []
    if not settings.auth_password:
        missing.append("AUTH_PASSWORD")
    if not settings.auth_session_secret:
        missing.append("AUTH_SESSION_SECRET")
    return _check(
        "auth configured",
        "ok" if not missing else "fail",
        "configured" if not missing else f"missing {', '.join(missing)}",
    )
