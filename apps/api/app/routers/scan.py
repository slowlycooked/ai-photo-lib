from __future__ import annotations

import threading

from fastapi import APIRouter

from ..database import SessionLocal
from ..schemas.scan import ScanStatus
from ..services.scanner import scan_directory, scan_state

router = APIRouter(prefix="/scan", tags=["scan"])


def _run_scan():
    """Run scan in a background thread with its own DB session."""
    db = SessionLocal()
    try:
        scan_directory(db)
    finally:
        db.close()


@router.post("/start")
def start_scan():
    if scan_state["running"]:
        return {"message": "Scan already in progress", "status": ScanStatus(**scan_state)}
    thread = threading.Thread(target=_run_scan, daemon=True, name="photo-scanner")
    thread.start()
    return {"message": "Scan started", "status": ScanStatus(**scan_state)}


@router.get("/status", response_model=ScanStatus)
def get_scan_status():
    return ScanStatus(**scan_state)
