from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from .routers import health, photos, scan, ai, search, tags, settings, projects

app = FastAPI(
    title="AI Photo Library API",
    version="0.6.0",
    description="Private AI-powered photo library for Synology NAS",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8088"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable, please try again later"},
    )


app.include_router(health.router)
app.include_router(projects.router)
app.include_router(photos.router)
app.include_router(scan.router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(tags.router)
app.include_router(settings.router)
