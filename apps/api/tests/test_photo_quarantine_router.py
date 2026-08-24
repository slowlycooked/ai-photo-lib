from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, require_project, require_project_manager
from app.database import get_db
from app.models.project import Project
from app.schemas.user import CurrentUser
from app.routers import photo_quarantine as quarantine_router
from app.services.photo_quarantine_service import (
    QuarantineBatchItemResult,
    QuarantineBatchResult,
)


class _FakeQuarantineService:
    def __init__(self, _db) -> None:
        pass

    def batch_action(
        self,
        *,
        project_id: int,
        item_ids: list[int],
        action: str,
        labeled_by: str,
    ):
        assert project_id == 1
        assert item_ids == [7]
        assert action == "RESTORE"
        assert labeled_by == "reviewer"
        return QuarantineBatchResult(
            results=[
                QuarantineBatchItemResult(
                    item_id=7,
                    error_code="conflict",
                    message="Original path is occupied; no file was overwritten",
                )
            ]
        )

    def calibration_report(self, *, project_id: int):
        assert project_id == 1
        return {
            "labeled_total": 1,
            "human_keep": 1,
            "human_trash": 0,
            "true_positive": 0,
            "false_positive": 1,
            "true_negative": 0,
            "false_negative": 0,
            "precision": 0.0,
            "recall": None,
            "false_positive_rate": 1.0,
            "target_sample_size": 300,
            "minimum_per_label": 100,
            "sample_target_met": False,
            "class_balance_met": False,
            "zero_false_positive_met": False,
            "ready_for_auto_move": False,
            "categories": [{
                "classification": "accidental_capture",
                "labeled_total": 1,
                "human_keep": 1,
                "human_trash": 0,
                "true_positive": 0,
                "false_positive": 1,
                "true_negative": 0,
                "false_negative": 0,
            }],
        }

    def list_labeled_items(self, *, project_id: int):
        assert project_id == 1
        return []


def _build_client(monkeypatch, *, forbidden: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(quarantine_router.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=9,
        username="reviewer",
        role="project_manager",
    )
    app.dependency_overrides[require_project] = lambda: Project(
        id=1,
        name="test",
        photo_library_path="/tmp/photos",
        thumbnail_path="/tmp/thumbs",
    )
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


def test_calibration_endpoint_returns_false_positive_risk(monkeypatch) -> None:
    response = _build_client(monkeypatch).get(
        "/api/projects/1/photo-quarantine/calibration"
    )

    assert response.status_code == 200
    assert response.json()["false_positive"] == 1
    assert response.json()["ready_for_auto_move"] is False


def test_calibration_csv_has_auditable_header(monkeypatch) -> None:
    response = _build_client(monkeypatch).get(
        "/api/projects/1/photo-quarantine/calibration.csv"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("item_id,photo_id,classification,model_decision")
