from __future__ import annotations

import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from ._version import APP_VERSION
from .database import SessionLocal
from .logging_config import setup_logging, should_log_request_debug_middleware
from .routers import (
    health,
    photos,
    scan,
    ai,
    search,
    tags,
    settings,
    projects,
    folders,
    project_scan,
    project_ai_jobs,
    project_ai_settings,
    project_prompt_templates,
    project_embeddings,
    project_search,
    project_tags,
    project_photos,
)
from .schemas.debug_config import build_default_debug_config
from .services.runtime_settings_service import (
    RuntimeSettingsService,
    RuntimeSettingsStorageUnavailableError,
)

logger = logging.getLogger(__name__)

setup_logging(build_default_debug_config())

app = FastAPI(
    title="AI Photo Library API",
    version=APP_VERSION,
    description="Private AI-powered photo library for Synology NAS",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8088"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
def load_runtime_debug_config() -> None:
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


@app.middleware("http")
async def request_debug_middleware(request: Request, call_next):
    if not should_log_request_debug_middleware():
        return await call_next(request)

    request_logger = logging.getLogger("ai_photo_lib.backend.http")
    started = perf_counter()
    body = await request.body()

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    debug_request = Request(request.scope, receive)
    request_logger.debug(
        "HTTP request start method=%s path=%s query=%s body=%s",
        request.method,
        request.url.path,
        request.url.query,
        body.decode("utf-8", errors="replace")[:2000],
    )
    response = await call_next(debug_request)
    request_logger.debug(
        "HTTP request end method=%s path=%s status_code=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - started) * 1000,
    )
    return response


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable, please try again later"},
    )


app.include_router(health.router)
app.include_router(projects.router)
app.include_router(folders.router)
app.include_router(photos.router)
app.include_router(scan.router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(tags.router)
app.include_router(settings.router)
# ── project-scoped routers (Phase 1 split) ───────────────────────────────────
app.include_router(project_photos.router)
app.include_router(project_scan.router)
app.include_router(project_ai_jobs.router)
app.include_router(project_ai_settings.router)
app.include_router(project_prompt_templates.router)
app.include_router(project_embeddings.router)
app.include_router(project_search.router)
app.include_router(project_tags.router)
