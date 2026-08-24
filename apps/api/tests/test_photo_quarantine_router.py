from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import require_project_manager
from app.database import get_db
from app.models.project import Project
from app.routers import photo_quarantine as quarantine_router
from app.services.photo_quarantine_service import (
    QuarantineBatchItemResult,
    QuarantineBatchResult,
)


class _FakeQuarantineService:
    def __init__(self, _db) -> None:
        pass

    def batch_action(self, *, project_id: int, item_ids: list[int], action: str):
        assert project_id == 1
        assert item_ids == [7]
        assert action == "RESTORE"
        return QuarantineBatchResult(
            results=[
                QuarantineBatchItemResult(
                    item_id=7,
                    error_code="conflict",
                    message="Original path is occupied; no file was overwritten",
                )
            ]
        )


def _build_client(monkeypatch, *, forbidden: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(quarantine_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: object()
    if forbidden:
        def reject_manager():
            raise HTTPException(status_code=403, detail="Project manager access required")

        app.dependency_overrides[require_project_manager] = reject_manager
    else:
        app.dependency_overrides[require_project_manager] = lambda: Project(
            id=1,
            name="test",
            photo_library_path="/tmp/photos",
            thumbnail_path="/tmp/thumbs",
        )
    monkeypatch.setattr(quarantine_router, "PhotoQuarantineService", _FakeQuarantineService)
    return TestClient(app)


def test_batch_endpoint_returns_per_item_conflict(monkeypatch) -> None:
    response = _build_client(monkeypatch).post(
        "/api/projects/1/photo-quarantine/batches",
        json={"action": "RESTORE", "item_ids": [7]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "requested": 1,
        "succeeded": 0,
        "failed": 1,
        "results": [{
            "item_id": 7,
            "succeeded": False,
            "item": None,
            "error_code": "conflict",
            "message": "Original path is occupied; no file was overwritten",
        }],
    }


def test_batch_endpoint_requires_project_manager(monkeypatch) -> None:
    response = _build_client(monkeypatch, forbidden=True).post(
        "/api/projects/1/photo-quarantine/batches",
        json={"action": "RESTORE", "item_ids": [7]},
    )

    assert response.status_code == 403


def test_batch_endpoint_rejects_duplicate_ids_before_service(monkeypatch) -> None:
    response = _build_client(monkeypatch).post(
        "/api/projects/1/photo-quarantine/batches",
        json={"action": "RESTORE", "item_ids": [7, 7]},
    )

    assert response.status_code == 422
