from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.aijob_app_service import AIJobAppService  # noqa: E402
from app.services.face_scan_service import FaceScanResult  # noqa: E402
from app.services.unknown_face_clustering_service import (  # noqa: E402
    UnknownFaceClusteringResult,
)


class _FakeDB:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def flush(self) -> None:
        self.flushes += 1


class AIJobAppServiceFaceScanTest(unittest.TestCase):
    def test_face_scan_job_clusters_unknown_faces_for_current_photo(self) -> None:
        db = _FakeDB()
        job = SimpleNamespace(
            status="running",
            error_message=None,
            parse_error=None,
            raw_model_output=None,
            finished_at=None,
            updated_at=None,
            retry_count=0,
            last_error_code=None,
            last_error_at=None,
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            lease_expires_at=None,
        )
        photo = SimpleNamespace(id=101)

        with patch("app.services.aijob_app_service.FaceScanService.scan_photo") as mock_scan, patch(
            "app.services.aijob_app_service.cluster_unknown_faces"
        ) as mock_cluster:
            mock_scan.return_value = FaceScanResult(
                project_id=1,
                photo_id=101,
                provider="opencv",
                detector_model="yunet",
                embedding_model="fake-sface",
                faces_detected=2,
                detections_created=2,
                detections_updated=0,
                embeddings_created=2,
                embeddings_updated=0,
                auto_assigned=0,
                review_pending=0,
                failures=0,
                message="Face scan completed",
            )
            mock_cluster.return_value = UnknownFaceClusteringResult(
                project_id=1,
                clusters_created=1,
                persons_created=1,
                faces_clustered=2,
                assignments_created=2,
            )

            AIJobAppService(db)._process_face_scan_job(job, photo, 1)

        mock_cluster.assert_called_once_with(
            db,
            project_id=1,
            max_faces=2,
            photo_ids=[101],
        )
        self.assertEqual(job.status, "success")
        self.assertIn("review_pending=2", job.raw_model_output)
        self.assertIn("cluster_assignments_created=2", job.raw_model_output)
        # Transaction management moved to Worker layer; service only flushes
        self.assertEqual(db.flushes, 1)
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
