from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from ._version import APP_VERSION
from .config import settings, warn_unknown_config_keys, enforce_managed_config_keys
from .database import SessionLocal, engine
from .logging_config import (
    _NOISY_PATH_RE,
    project_id_ctx,
    request_id_ctx,
    setup_logging,
    should_log_request_debug_middleware,
)
from .routers import (
    auth,
    health,
    settings as settings_router,
    projects,
    folders,
    project_scan,
    project_ai_jobs,
    project_ai_settings,
    project_embedding_settings,
    project_prompt_templates,
    project_embeddings,
    project_search,
    project_search_settings,
    project_query_planner_settings,
    project_tags,
    project_tasks,
    project_photos,
    project_face_settings,
    project_faces,
    project_people,
)
from .schemas.debug_config import build_default_debug_config
from .services.auth_service import (
    SESSION_COOKIE_NAME,
    auth_password_configured,
    create_session_cookie,
    verify_session_cookie,
)
from .services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)
from .services.startup_schema_service import (
    StartupSchemaCheckError,
    validate_required_columns,
    validate_required_tables,
)

logger = logging.getLogger(__name__)

setup_logging(build_default_debug_config())


def load_runtime_debug_config() -> None:
    warn_unknown_config_keys()
    enforce_managed_config_keys()

    try:
        validate_required_tables(engine)
        validate_required_columns(engine)
    except StartupSchemaCheckError:
        logger.exception("Startup schema self-check failed")
        raise

    db = SessionLocal()
    try:
        config = RuntimeSettingsService.get_debug_config(db)
    except RuntimeSettingsStorageUnavailableError as exc:
        logger.warning("Runtime debug config unavailable at startup: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to apply startup debug config: %s", exc)
    else:
        setup_logging(config)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    load_runtime_debug_config()
    yield


app = FastAPI(
    title="AI Photo Library API",
    version=APP_VERSION,
    description="Private AI-powered photo library for local native deployment",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


_PROJECT_ID_RE = re.compile(r"^/projects/(\d+)")
_AUTH_EXEMPT_PATHS = ("/health", "/auth/login", "/auth/logout")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not settings.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if request.method == "OPTIONS" or path in _AUTH_EXEMPT_PATHS:
        return await call_next(request)

    if not auth_password_configured():
        return JSONResponse(
            status_code=503,
            content={"detail": "AUTH_PASSWORD is not configured"},
        )

    session = verify_session_cookie(request.cookies.get(SESSION_COOKIE_NAME))
    if session is None:
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    response = await call_next(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_cookie(str(session["sub"])),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=settings.auth_session_timeout_minutes * 60,
        path="/",
    )
    return response


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach request_id / project_id context vars and emit a single structured
    request log line.  High-frequency noisy routes are suppressed at DEBUG unless
    they are slow or return an error.
    """
    rid = str(uuid.uuid4())[:8]
    path = request.url.path

    # Derive project_id from path when present
    m = _PROJECT_ID_RE.match(path)
    pid = m.group(1) if m else None

    req_token = request_id_ctx.set(rid)
    proj_token = project_id_ctx.set(pid)

    request_logger = logging.getLogger("ai_photo_lib.backend.http")
    is_debug_middleware = should_log_request_debug_middleware()
    is_trace = request_logger.isEnabledFor(5)  # TRACE_LEVEL_NUM

    # TRACE: log request start + query/body
    if is_trace:
        body = await request.body()

        async def _receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, _receive)
        request_logger.log(
            5,
            "http_request_start request_id=%s method=%s path=%s query=%s body=%s",
            rid,
            request.method,
            path,
            request.url.query,
            body.decode("utf-8", errors="replace")[:500],
        )

    started = perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(req_token)
        project_id_ctx.reset(proj_token)

    duration_ms = (perf_counter() - started) * 1000
    status_code = response.status_code
    is_error = status_code >= 400
    is_slow = duration_ms >= 1000
    is_noisy = bool(_NOISY_PATH_RE.match(path))

    if is_debug_middleware:
        # Always log errors and slow requests; suppress noisy routes otherwise
        if is_error or is_slow or not is_noisy:
            request_logger.debug(
                "http_request request_id=%s method=%s path=%s status=%d duration_ms=%.2f project_id=%s",
                rid,
                request.method,
                path,
                status_code,
                duration_ms,
                pid,
                extra={"path": path, "status_code": status_code, "duration_ms": duration_ms},
            )

    return response


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable, please try again later"},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(folders.router)
app.include_router(settings_router.router)
# ── project-scoped routers ────────────────────────────────────────────────────
app.include_router(project_photos.router)
app.include_router(project_scan.router)
app.include_router(project_ai_jobs.router)
app.include_router(project_ai_settings.router)
app.include_router(project_embedding_settings.router)
app.include_router(project_prompt_templates.router)
app.include_router(project_embeddings.router)
app.include_router(project_search.router)
app.include_router(project_search_settings.router)
app.include_router(project_query_planner_settings.router)
app.include_router(project_tags.router)
app.include_router(project_tasks.router)
app.include_router(project_face_settings.router)
app.include_router(project_faces.router)
app.include_router(project_people.router)
