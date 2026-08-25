from __future__ import annotations

from types import SimpleNamespace

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
    QuarantineReconciliationResult,
)


class _FakeQuarantineService:
    last_list_args = None

    def __init__(self, _db) -> None:
        pass

    def list_items(self, **kwargs):
        self.__class__.last_list_args = kwargs
        return 0, []

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

    def request_delete(self, *, project_id: int, item_id: int, labeled_by: str):
        assert project_id == 1
        assert item_id == 7
        assert labeled_by == "reviewer"
        from app.services.photo_quarantine_service import PhotoQuarantineConflict

        raise PhotoQuarantineConflict("already queued")

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

    def reconcile_deleted(self, *, project_id: int):
        assert project_id == 1
        return QuarantineReconciliationResult(
            checked=3,
            confirmed=2,
            remaining=1,
            failed=0,
        )


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


def test_list_endpoint_passes_classification_filter(monkeypatch) -> None:
    response = _build_client(monkeypatch).get(
        "/api/projects/1/photo-quarantine/items",
        params={"classification": "suspected_duplicate"},
    )

    assert response.status_code == 200
    assert response.json() == {"total": 0, "items": []}
    assert _FakeQuarantineService.last_list_args["classification"] == "suspected_duplicate"


def test_batch_endpoint_requires_project_manager(monkeypatch) -> None:
    response = _build_client(monkeypatch, forbidden=True).post(
        "/api/projects/1/photo-quarantine/batches",
        json={"action": "RESTORE", "item_ids": [7]},
    )

    assert response.status_code == 403


def test_request_delete_endpoint_uses_explicit_approval_route(monkeypatch) -> None:
    response = _build_client(monkeypatch).post(
        "/api/projects/1/photo-quarantine/items/7/request-delete"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "already queued"}


def test_reconciliation_endpoint_reports_automatic_confirmations(monkeypatch) -> None:
    response = _build_client(monkeypatch).post(
        "/api/projects/1/photo-quarantine/reconciliations"
    )

    assert response.status_code == 200
    assert response.json() == {
        "checked": 3,
        "confirmed": 2,
        "remaining": 1,
        "failed": 0,
    }


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


def test_start_run_reads_enqueued_task_with_keyword_scope(monkeypatch) -> None:
    class _FakeTaskService:
        def __init__(self, _db) -> None:
            pass

        def get_task(self, *, project_id: int, task_id: int):
            assert project_id == 1
            assert task_id == 88
            return {
                "id": 88,
                "project_id": 1,
                "task_type": "photo_quarantine_analysis",
                "status": "queued",
                "retry_count": 0,
                "request_params": {"trigger": "manual"},
                "progress_payload": None,
                "result_payload": None,
                "error_message": None,
                "created_at": "2026-08-24T21:00:00Z",
                "updated_at": "2026-08-24T21:00:00Z",
                "started_at": None,
                "finished_at": None,
            }

    monkeypatch.setattr(
        quarantine_router,
        "enqueue_photo_quarantine_task",
        lambda *_args, **_kwargs: SimpleNamespace(task=SimpleNamespace(id=88)),
    )
    monkeypatch.setattr(
        quarantine_router,
        "ProjectTasksAppService",
        _FakeTaskService,
    )

    response = _build_client(monkeypatch).post(
        "/api/projects/1/photo-quarantine/runs"
    )

    assert response.status_code == 200
    assert response.json()["id"] == 88
