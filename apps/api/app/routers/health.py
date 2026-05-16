from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check():
    return {"status": "ok", "version": "0.4.0", "service": "ai-photo-lib"}
