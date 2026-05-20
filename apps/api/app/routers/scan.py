from __future__ import annotations

import logging
import threading

from fastapi import APIRouter

from ..database import SessionLocal
from ..schemas.scan import ScanStatus
from ..services.scanner import scan_directory, scan_state

logger = logging.getLogger(__name__)

# DEPRECATED: Use /projects/{project_id}/scan/* instead.
# These endpoints remain for backward-compatibility only and will be removed.

router = APIRouter(prefix="/scan", tags=["scan [deprecated]"])

_DEPRECATION_MSG = (
    "Global /scan/* endpoints are deprecated. "
    "Use /projects/{project_id}/scan/* instead."
)


def _run_scan():
    """Run scan in a background thread with its own DB session."""
    db = SessionLocal()
    try:
        scan_directory(db)
    finally:
        db.close()


@router.post("/start", deprecated=True)
def start_scan():
    """[DEPRECATED] Use POST /projects/{project_id}/scan/start instead."""
    logger.warning(_DEPRECATION_MSG)
    if scan_state["running"]:
        return {"message": "Scan already in progress", "status": ScanStatus(**scan_state)}
    thread = threading.Thread(target=_run_scan, daemon=True, name="photo-scanner")
    thread.start()
    return {"message": "Scan started", "status": ScanStatus(**scan_state)}


@router.get("/status", response_model=ScanStatus, deprecated=True)
def get_scan_status():
    """[DEPRECATED] Use GET /projects/{project_id}/scan/status instead."""
    logger.warning(_DEPRECATION_MSG)
    return ScanStatus(**scan_state)
