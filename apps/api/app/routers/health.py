from fastapi import APIRouter

from .._version import APP_VERSION

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check():
    return {"status": "ok", "version": APP_VERSION, "service": "ai-photo-lib"}
