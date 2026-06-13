from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.ai import AIJob  # noqa: E402
from app.models.photo import Photo  # noqa: E402,F401
from app.models.project import Project  # noqa: E402,F401
from app.models.project_task import ProjectTask  # noqa: E402
from app.services.task_claim_service import TaskClaimService, _QueueCandidate  # noqa: E402


SCHEMA_SQL = """
CREATE TABLE ai_jobs (
    id INTEGER PRIMARY KEY,
    photo_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    job_type TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    locked_by TEXT,
    locked_at TEXT,
    heartbeat_at TEXT,
    lease_expires_at TEXT,
    last_error_code TEXT,
    last_error_at TEXT,
    prompt_template_id INTEGER,
    prompt_version INTEGER,
    model_name TEXT,
    model_params TEXT,
    raw_model_output TEXT,
    parse_error TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_tasks (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    retry_count INTEGER NOT NULL DEFAULT 0,
    request_params TEXT,
    progress_payload TEXT,
    result_payload TEXT,
    error_message TEXT,
    locked_by TEXT,
    locked_at TEXT,
    heartbeat_at TEXT,
    lease_expires_at TEXT,
    last_error_code TEXT,
    last_error_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class TaskClaimServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._engine = create_engine(
            f"sqlite:///{self._tmp.name}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self._SessionLocal = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            future=True,
        )
        with self._engine.begin() as conn:
            for stmt in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
                conn.execute(sa.text(stmt))

    def tearDown(self) -> None:
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_claim_next_returns_none_when_no_queued_work_exists(self) -> None:
        with self._SessionLocal() as db:
            db.add(
                ProjectTask(
                    project_id=1,
                    task_type="library_scan",
                    status="success",
                )
            )
            db.commit()

            self.assertIsNone(TaskClaimService(db).claim_next())

    def test_claim_next_prefers_older_project_task(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0)
        with self._SessionLocal() as db:
            task = ProjectTask(
                project_id=1,
                task_type="library_scan",
                status="queued",
                created_at=base,
            )
            job = AIJob(
                id=1,
                project_id=1,
                photo_id=1,
                job_type="analysis",
                status="queued",
                created_at=base + timedelta(seconds=1),
            )
            db.add_all([task, job])
            db.commit()

            claimed = TaskClaimService(db).claim_next()

            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.kind, "project_task")
            self.assertEqual(claimed.item.id, task.id)
            self.assertEqual(claimed.item.status, "running")
            self.assertIsNotNone(claimed.item.locked_by)
            self.assertIsNotNone(claimed.item.locked_at)
            self.assertIsNotNone(claimed.item.heartbeat_at)
            self.assertIsNotNone(claimed.item.lease_expires_at)

    def test_claim_next_prefers_older_ai_job(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0)
        with self._SessionLocal() as db:
            job = AIJob(
                id=1,
                project_id=1,
                photo_id=1,
                job_type="analysis",
                status="queued",
                created_at=base,
            )
            task = ProjectTask(
                project_id=1,
                task_type="library_scan",
                status="queued",
                created_at=base + timedelta(seconds=1),
            )
            db.add_all([job, task])
            db.commit()

            claimed = TaskClaimService(db).claim_next()

            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.kind, "ai_job")
            self.assertEqual(claimed.item.id, job.id)
            self.assertEqual(claimed.item.status, "running")
            self.assertIsNotNone(claimed.item.locked_by)
            self.assertIsNotNone(claimed.item.locked_at)
            self.assertIsNotNone(claimed.item.heartbeat_at)
            self.assertIsNotNone(claimed.item.lease_expires_at)

    def test_claim_next_locks_only_selected_queue(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0)
        with self._SessionLocal() as db:
            task = ProjectTask(
                project_id=1,
                task_type="library_scan",
                status="queued",
                created_at=base,
            )
            job = AIJob(
                id=1,
                project_id=1,
                photo_id=1,
                job_type="analysis",
                status="queued",
                created_at=base + timedelta(seconds=1),
            )
            db.add_all([task, job])
            db.commit()

            class _SpyClaimService(TaskClaimService):
                ai_job_claim_calls = 0

                def _claim_ai_job(self, job_id: int):  # type: ignore[no-untyped-def]
                    self.ai_job_claim_calls += 1
                    return super()._claim_ai_job(job_id)

            service = _SpyClaimService(db)
            claimed = service.claim_next()

            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.kind, "project_task")
            self.assertEqual(service.ai_job_claim_calls, 0)

    def test_claim_next_falls_back_when_older_candidate_cannot_be_locked(self) -> None:
        base = datetime(2026, 1, 1, 12, 0, 0)

        class _FallbackClaimService(TaskClaimService):
            def _peek_next_project_task(self):
                return _QueueCandidate(kind="project_task", id=10, created_at=base)

            def _peek_next_ai_job(self):
                return _QueueCandidate(
                    kind="ai_job",
                    id=20,
                    created_at=base + timedelta(seconds=1),
                )

            def _claim_project_task(self, task_id: int):
                return None

            def _claim_ai_job(self, job_id: int):
                return AIJob(
                    id=job_id,
                    project_id=1,
                    photo_id=1,
                    job_type="analysis",
                    status="queued",
                    created_at=base + timedelta(seconds=1),
                )

        with self._SessionLocal() as db:
            claimed = _FallbackClaimService(db).claim_next()

        self.assertIsNotNone(claimed)
        assert claimed is not None
        self.assertEqual(claimed.kind, "ai_job")
        self.assertEqual(claimed.item.id, 20)

    def test_recover_stuck_running_tasks_applies_task_type_policy(self) -> None:
        expired_at = datetime.utcnow() - timedelta(minutes=5)
        with self._SessionLocal() as db:
            db.add_all(
                [
                    ProjectTask(
                        project_id=1,
                        task_type="library_scan",
                        status="running",
                        retry_count=0,
                        progress_payload={
                            "running": True,
                            "scanned": 12,
                            "current_path": "/tmp/a.jpg",
                        },
                        lease_expires_at=expired_at,
                    ),
                    ProjectTask(
                        project_id=1,
                        task_type="unknown_face_clustering",
                        status="running",
                        retry_count=0,
                        progress_payload={"running": True, "clusters_created": 2},
                        lease_expires_at=expired_at,
                    ),
                    AIJob(
                        id=99,
                        project_id=1,
                        photo_id=1,
                        job_type="analysis",
                        status="running",
                        retry_count=0,
                        lease_expires_at=expired_at,
                    ),
                ]
            )
            db.commit()

            result = TaskClaimService(db).recover_stuck_running_tasks()

            self.assertEqual(result["project_tasks"], 2)
            self.assertEqual(result["ai_jobs"], 1)

            scan_task = db.query(ProjectTask).filter(ProjectTask.task_type == "library_scan").first()
            assert scan_task is not None
            self.assertEqual(scan_task.status, "queued")
            self.assertFalse(scan_task.progress_payload["running"])
            self.assertEqual(scan_task.progress_payload["recovery_policy"], "resume_from_checkpoint")
            self.assertEqual(scan_task.progress_payload["scanned"], 12)

            cluster_task = db.query(ProjectTask).filter(
                ProjectTask.task_type == "unknown_face_clustering"
            ).first()
            assert cluster_task is not None
            self.assertEqual(cluster_task.status, "failed")
            self.assertEqual(cluster_task.progress_payload["recovery_policy"], "fail")
            self.assertEqual(cluster_task.last_error_code, "lease_expired")

            job = db.query(AIJob).filter(AIJob.id == 99).first()
            assert job is not None
            self.assertEqual(job.status, "queued")
            self.assertEqual(job.last_error_code, "lease_expired")


if __name__ == "__main__":
    unittest.main()
