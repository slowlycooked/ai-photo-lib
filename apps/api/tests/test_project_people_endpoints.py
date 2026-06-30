from __future__ import annotations

import os
import tempfile
import unittest
from collections.abc import Generator

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.api.deps import get_current_user  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.user import CurrentUser  # noqa: E402


SCHEMA_SQL = """
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  photo_library_path TEXT NOT NULL,
  thumbnail_path TEXT,
  is_default BOOLEAN NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at TEXT
);

CREATE TABLE persons (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  display_name TEXT NOT NULL,
  normalized_name TEXT,
  is_named BOOLEAN NOT NULL DEFAULT 0,
  representative_face_detection_id INTEGER,
  sample_count INTEGER NOT NULL DEFAULT 0,
  confirmed_sample_count INTEGER NOT NULL DEFAULT 0,
  auto_assigned_count INTEGER NOT NULL DEFAULT 0,
  review_pending_count INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL DEFAULT 'system',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE face_negative_constraints (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  face_detection_id INTEGER NOT NULL,
  not_person_id INTEGER NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE face_detections (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  bbox_x INTEGER NOT NULL,
  bbox_y INTEGER NOT NULL,
  bbox_w INTEGER NOT NULL,
  bbox_h INTEGER NOT NULL,
  detection_confidence REAL,
  face_quality_score REAL,
  face_crop_path TEXT,
  face_crop_hash TEXT,
  status TEXT NOT NULL DEFAULT 'embedded',
  error_message TEXT,
  detected_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_face_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  face_recognition_enabled BOOLEAN NOT NULL DEFAULT 0,
  face_provider TEXT NOT NULL DEFAULT 'opencv',
  face_detector_model TEXT NOT NULL DEFAULT 'yunet',
  face_embedding_model TEXT NOT NULL DEFAULT 'sface',
  face_runtime TEXT NOT NULL DEFAULT 'cpu',
  store_face_crops BOOLEAN NOT NULL DEFAULT 1,
  face_crop_storage TEXT NOT NULL DEFAULT 'local',
  auto_accept_threshold REAL NOT NULL DEFAULT 0.62,
  review_threshold REAL NOT NULL DEFAULT 0.48,
  cluster_threshold REAL NOT NULL DEFAULT 0.50,
  min_face_size INTEGER NOT NULL DEFAULT 40,
  min_detection_confidence REAL NOT NULL DEFAULT 0.75,
  min_quality_for_prototype REAL NOT NULL DEFAULT 0.70,
  max_positive_samples_per_person INTEGER NOT NULL DEFAULT 200,
  allow_auto_assignment BOOLEAN NOT NULL DEFAULT 1,
  require_human_confirmation_for_new_person BOOLEAN NOT NULL DEFAULT 1,
  enable_negative_constraints BOOLEAN NOT NULL DEFAULT 1,
  enable_person_cannot_links BOOLEAN NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE person_cannot_links (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  person_id_a INTEGER NOT NULL,
  person_id_b INTEGER NOT NULL,
  source TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (project_id, person_id_a, person_id_b)
);

CREATE TABLE person_face_assignments (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  person_id INTEGER NOT NULL,
  face_detection_id INTEGER NOT NULL,
  assignment_status TEXT NOT NULL,
  assignment_source TEXT NOT NULL,
  confidence REAL,
  similarity_score REAL,
  is_positive_sample BOOLEAN NOT NULL DEFAULT 0,
  is_training_candidate BOOLEAN NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_tasks (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  task_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  retry_count INTEGER NOT NULL DEFAULT 0,
  request_params JSON,
  progress_payload JSON,
  result_payload JSON,
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

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO persons (
  id, project_id, display_name, normalized_name, is_named,
  representative_face_detection_id, sample_count, confirmed_sample_count,
  auto_assigned_count, review_pending_count, created_by
) VALUES
  (101, 1, '爸爸', '爸爸', 1, 301, 8, 5, 2, 1, 'user'),
  (102, 1, '人物 2', '人物 2', 0, NULL, 0, 0, 0, 0, 'system'),
  (201, 2, 'Project B Person', 'project b person', 1, 401, 1, 1, 0, 0, 'system');

INSERT INTO face_detections (
  id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, status
) VALUES
  (301, 1, 11, 10, 10, 20, 20, 'embedded'),
  (302, 1, 12, 15, 15, 18, 18, 'embedded'),
  (401, 2, 21, 12, 12, 16, 16, 'embedded');

INSERT INTO person_face_assignments (
  id, project_id, person_id, face_detection_id, assignment_status,
  assignment_source, confidence, similarity_score, is_positive_sample, is_training_candidate
) VALUES
  (501, 1, 101, 301, 'human_confirmed', 'human_label', 0.99, 0.88, 1, 1),
  (502, 1, 101, 302, 'review_pending', 'similarity_match', 0.74, 0.69, 0, 1),
  (601, 2, 201, 401, 'human_confirmed', 'human_label', 0.98, 0.91, 1, 1);
"""


class ProjectPeopleEndpointsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._auth_enabled_before = settings.auth_enabled
        settings.auth_enabled = False
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._engine = sa.create_engine(
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
            for stmt in [part.strip() for part in SEED_SQL.split(";") if part.strip()]:
                conn.execute(sa.text(stmt))

        def override_get_db() -> Generator[Session, None, None]:
            db = self._SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_get_current_user() -> CurrentUser:
            return CurrentUser(
                id=None,
                username="test-admin",
                display_name="Test Admin",
                role="admin",
                bootstrap=True,
            )

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        settings.auth_enabled = self._auth_enabled_before
        app.dependency_overrides.clear()
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_project_people_list_is_scoped(self) -> None:
        res = self.client.get("/projects/1/people")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["items"][0]["id"], 101)
        self.assertEqual(body["items"][0]["display_name"], "爸爸")

    def test_project_person_detail_returns_assignments(self) -> None:
        res = self.client.get("/projects/1/people/101")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["id"], 101)
        self.assertEqual(len(body["assignments"]), 2)
        self.assertEqual(body["assignments"][0]["face_detection"]["project_id"], 1)

    def test_project_cannot_read_other_project_person(self) -> None:
        res = self.client.get("/projects/1/people/201")
        self.assertEqual(res.status_code, 404)

    def test_can_rename_person(self) -> None:
      res = self.client.patch(
        "/projects/1/people/102",
        json={"display_name": "妈妈"},
      )
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["person"]["display_name"], "妈妈")
      self.assertTrue(body["person"]["is_named"])

    def test_renaming_unnamed_cluster_promotes_active_faces_to_positive_samples(self) -> None:
      with self._engine.begin() as conn:
        conn.execute(
          sa.text(
            """
            INSERT INTO face_detections (
              id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, status
            )
            VALUES (303, 1, 13, 18, 18, 20, 20, 'embedded')
            """
          )
        )
        conn.execute(
          sa.text(
            """
            INSERT INTO person_face_assignments (
              id, project_id, person_id, face_detection_id, assignment_status,
              assignment_source, confidence, similarity_score, is_positive_sample, is_training_candidate
            )
            VALUES (503, 1, 102, 303, 'review_pending', 'unknown_cluster', 0.73, 0.64, 0, 1)
            """
          )
        )

      res = self.client.patch(
        "/projects/1/people/102",
        json={"display_name": "妈妈"},
      )

      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["person"]["sample_count"], 1)
      self.assertEqual(body["person"]["confirmed_sample_count"], 1)
      self.assertEqual(body["person"]["review_pending_count"], 0)
      self.assertTrue(body["feedback_effects"]["prototype_rebuilt"])
      self.assertEqual(body["feedback_effects"]["rebuilt_person_ids"], [102])
      self.assertEqual(body["feedback_effects"]["unknown_rematch_scope"], "person")
      self.assertEqual(body["feedback_effects"]["unknown_rematch_person_id"], 102)
      self.assertTrue(body["feedback_effects"]["unknown_rematch_task_created"])

      detail = self.client.get("/projects/1/people/102").json()
      target = [a for a in detail["assignments"] if a["face_detection_id"] == 303][0]
      self.assertEqual(target["assignment_status"], "human_confirmed")
      self.assertEqual(target["assignment_source"], "human_label")
      self.assertTrue(target["is_positive_sample"])

      with self._engine.connect() as conn:
        task = conn.execute(
          sa.text(
            """
            SELECT task_type, status, request_params
            FROM project_tasks
            WHERE project_id = 1
            """
          )
        ).first()
      self.assertIsNotNone(task)
      self.assertEqual(task[0], "face_rematch_unknown")
      self.assertEqual(task[1], "queued")

    def test_confirm_face_assignment_promotes_to_positive(self) -> None:
      res = self.client.post("/projects/1/people/101/faces/302/confirm")
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["person"]["confirmed_sample_count"], 2)
      self.assertEqual(body["person"]["review_pending_count"], 0)

      detail = self.client.get("/projects/1/people/101").json()
      target = [a for a in detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertEqual(target["assignment_status"], "human_confirmed")
      self.assertTrue(target["is_positive_sample"])

    def test_reject_face_assignment_creates_negative_constraint(self) -> None:
      res = self.client.post("/projects/1/people/101/faces/302/reject")
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["person"]["sample_count"], 1)

      with self._engine.connect() as conn:
        row = conn.execute(
          sa.text(
            """
            SELECT source
            FROM face_negative_constraints
            WHERE project_id = 1 AND face_detection_id = 302 AND not_person_id = 101
            """
          )
        ).first()
      self.assertIsNotNone(row)
      self.assertEqual(row[0], "human_rejected")

    def test_move_face_assignment_between_people(self) -> None:
      res = self.client.post(
        "/projects/1/people/101/faces/302/move",
        json={"target_person_id": 102},
      )
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["source_person"]["id"], 101)
      self.assertEqual(body["target_person"]["id"], 102)
      self.assertEqual(body["target_person"]["sample_count"], 1)
      self.assertEqual(body["target_person"]["confirmed_sample_count"], 1)

      source_detail = self.client.get("/projects/1/people/101").json()
      target_detail = self.client.get("/projects/1/people/102").json()
      target_assignment = [a for a in target_detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertFalse(any(a["face_detection_id"] == 302 for a in source_detail["assignments"]))
      self.assertEqual(target_assignment["assignment_status"], "human_corrected")

    def test_set_representative_face_requires_assignment(self) -> None:
      bad = self.client.post(
        "/projects/1/people/102/representative-face",
        json={"face_detection_id": 301},
      )
      self.assertEqual(bad.status_code, 422)

      move = self.client.post(
        "/projects/1/people/101/faces/302/move",
        json={"target_person_id": 102},
      )
      self.assertEqual(move.status_code, 200)

      ok = self.client.post(
        "/projects/1/people/102/representative-face",
        json={"face_detection_id": 302},
      )
      self.assertEqual(ok.status_code, 200)
      self.assertEqual(ok.json()["person"]["representative_face_detection_id"], 302)

    def test_cannot_mutate_other_project_face_or_person(self) -> None:
      res = self.client.post("/projects/1/people/101/faces/401/confirm")
      self.assertEqual(res.status_code, 404)

      res = self.client.patch(
        "/projects/1/people/201",
        json={"display_name": "x"},
      )
      self.assertEqual(res.status_code, 404)

    def test_review_pending_list_is_project_scoped(self) -> None:
      res = self.client.get("/projects/1/people/review")
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["total"], 1)
      self.assertEqual(body["items"][0]["person_id"], 101)
      self.assertEqual(body["items"][0]["face_detection_id"], 302)

    def test_batch_confirm_review_pending(self) -> None:
      with self._engine.begin() as conn:
        conn.execute(
          sa.text(
            """
            INSERT INTO person_face_assignments (
              id, project_id, person_id, face_detection_id, assignment_status,
              assignment_source, confidence, similarity_score, is_positive_sample, is_training_candidate
            )
            VALUES (503, 1, 102, 302, 'auto_assigned', 'similarity_match', 0.71, 0.66, 0, 1)
            """
          )
        )

      res = self.client.post(
        "/projects/1/people/101/review/batch-confirm",
        json={
          "face_detection_ids": [302],
          "request_id": "req-people-batch-1",
          "operator": "tester",
          "max_retries": 2,
        },
      )
      self.assertEqual(res.status_code, 200)
      self.assertEqual(res.json()["updated"], 1)
      self.assertEqual(res.json()["request_id"], "req-people-batch-1")
      self.assertEqual(res.json()["operator"], "tester")
      self.assertEqual(res.json()["attempts"], 1)

      detail = self.client.get("/projects/1/people/101").json()
      target = [a for a in detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertEqual(target["assignment_status"], "human_confirmed")
      self.assertTrue(target["is_positive_sample"])

      other_detail = self.client.get("/projects/1/people/102").json()
      other = [a for a in other_detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertEqual(other["assignment_status"], "rejected")

      with self._engine.connect() as conn:
        negative = conn.execute(
          sa.text(
            """
            SELECT source
            FROM face_negative_constraints
            WHERE project_id = 1 AND face_detection_id = 302 AND not_person_id = 102
            """
          )
        ).first()
      self.assertIsNotNone(negative)
      self.assertEqual(negative[0], "human_corrected")

    def test_batch_confirm_accepts_auto_assigned(self) -> None:
      with self._engine.begin() as conn:
        conn.execute(
          sa.text(
            """
            UPDATE person_face_assignments
            SET assignment_status = 'auto_assigned',
                assignment_source = 'similarity_match'
            WHERE id = 502
            """
          )
        )

      res = self.client.post(
        "/projects/1/people/101/review/batch-confirm",
        json={
          "face_detection_ids": [302],
          "request_id": "req-people-batch-auto",
        },
      )
      self.assertEqual(res.status_code, 200)
      self.assertEqual(res.json()["updated"], 1)

      detail = self.client.get("/projects/1/people/101").json()
      target = [a for a in detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertEqual(target["assignment_status"], "human_confirmed")
      self.assertTrue(target["is_positive_sample"])

    def test_batch_reject_and_move_review_pending(self) -> None:
      reject = self.client.post(
        "/projects/1/people/101/review/batch-reject",
        json={"face_detection_ids": [302]},
      )
      self.assertEqual(reject.status_code, 200)
      self.assertEqual(reject.json()["updated"], 1)

      # Reset assignment to review_pending for move test within same test case.
      with self._engine.begin() as conn:
        conn.execute(
          sa.text(
            """
            UPDATE person_face_assignments
            SET assignment_status = 'review_pending',
                assignment_source = 'similarity_match',
                is_positive_sample = 0,
                is_training_candidate = 1
            WHERE project_id = 1 AND person_id = 101 AND face_detection_id = 302
            """
          )
        )

      move = self.client.post(
        "/projects/1/people/101/review/batch-move",
        json={"face_detection_ids": [302], "target_person_id": 102},
      )
      self.assertEqual(move.status_code, 200)
      self.assertEqual(move.json()["updated"], 1)

      source_detail = self.client.get("/projects/1/people/101").json()
      target_detail = self.client.get("/projects/1/people/102").json()
      target_assignment = [a for a in target_detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertFalse(any(a["face_detection_id"] == 302 for a in source_detail["assignments"]))
      self.assertEqual(target_assignment["assignment_status"], "human_corrected")

    def test_create_empty_person(self) -> None:
      res = self.client.post(
        "/projects/1/people",
        json={"display_name": "朋友A", "is_named": True},
      )
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["person"]["display_name"], "朋友A")
      self.assertTrue(body["person"]["is_named"])
      self.assertEqual(body["person"]["sample_count"], 0)

    def test_merge_people_moves_active_assignments(self) -> None:
      res = self.client.post(
        "/projects/1/people/101/merge",
        json={"target_person_id": 102},
      )
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["moved_assignments"], 2)
      self.assertEqual(body["source_person"]["sample_count"], 0)
      self.assertEqual(body["target_person"]["sample_count"], 2)

      target_detail = self.client.get("/projects/1/people/102").json()
      moved_face_ids = {a["face_detection_id"] for a in target_detail["assignments"]}
      self.assertEqual(moved_face_ids, {301, 302})

    def test_split_people_creates_new_person_and_moves_selected_faces(self) -> None:
      res = self.client.post(
        "/projects/1/people/101/split",
        json={"face_detection_ids": [302], "new_display_name": "拆分人物"},
      )
      self.assertEqual(res.status_code, 200)
      body = res.json()
      self.assertEqual(body["moved_assignments"], 1)
      self.assertEqual(body["source_person"]["sample_count"], 1)
      self.assertEqual(body["target_person"]["display_name"], "拆分人物")
      self.assertEqual(body["target_person"]["sample_count"], 1)

      source_detail = self.client.get("/projects/1/people/101").json()
      self.assertFalse(any(a["face_detection_id"] == 302 for a in source_detail["assignments"]))

      target_id = body["target_person"]["id"]
      target_detail = self.client.get(f"/projects/1/people/{target_id}").json()
      target_assignment = [a for a in target_detail["assignments"] if a["face_detection_id"] == 302][0]
      self.assertEqual(target_assignment["assignment_status"], "human_corrected")

    def test_people_list_supports_filters(self) -> None:
      unnamed_only = self.client.get("/projects/1/people?is_named=false")
      self.assertEqual(unnamed_only.status_code, 200)
      unnamed_payload = unnamed_only.json()
      self.assertEqual(unnamed_payload["total"], 1)
      self.assertEqual(unnamed_payload["items"][0]["id"], 102)

      with_review = self.client.get("/projects/1/people?has_review_pending=true")
      self.assertEqual(with_review.status_code, 200)
      with_review_payload = with_review.json()
      self.assertEqual(with_review_payload["total"], 1)
      self.assertEqual(with_review_payload["items"][0]["id"], 101)

      by_query = self.client.get("/projects/1/people?q=爸爸")
      self.assertEqual(by_query.status_code, 200)
      by_query_payload = by_query.json()
      self.assertEqual(by_query_payload["total"], 1)
      self.assertEqual(by_query_payload["items"][0]["id"], 101)

    def test_delete_person_requires_no_active_assignments(self) -> None:
      blocked = self.client.delete("/projects/1/people/101")
      self.assertEqual(blocked.status_code, 409)

      with self._engine.begin() as conn:
        conn.execute(
          sa.text(
            """
            UPDATE person_face_assignments
            SET assignment_status = 'rejected',
                is_positive_sample = 0,
                is_training_candidate = 0
            WHERE project_id = 1 AND person_id = 101
            """
          )
        )

      ok = self.client.delete("/projects/1/people/101")
      self.assertEqual(ok.status_code, 200)
      self.assertTrue(ok.json()["deleted"])

      missing = self.client.get("/projects/1/people/101")
      self.assertEqual(missing.status_code, 404)

    def test_split_writes_cannot_link_and_merge_is_then_blocked(self) -> None:
        """After split, a PersonCannotLink row must exist and a re-merge attempt must return 409."""
        split_res = self.client.post(
            "/projects/1/people/101/split",
            json={"face_detection_ids": [302], "new_display_name": "拆分人物"},
        )
        self.assertEqual(split_res.status_code, 200)
        new_person_id = split_res.json()["target_person"]["id"]

        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT COUNT(*) FROM person_cannot_links WHERE project_id = 1")
            ).scalar()
        self.assertEqual(row, 1, "Expected exactly one PersonCannotLink after split")

        merge_res = self.client.post(
            "/projects/1/people/101/merge",
            json={"target_person_id": new_person_id},
        )
        self.assertEqual(
            merge_res.status_code,
            409,
            f"Expected 409 (cannot-link), got {merge_res.status_code}: {merge_res.text}",
        )

    def test_split_does_not_write_cannot_link_when_flag_disabled(self) -> None:
        """When enable_person_cannot_links=False, split must NOT write a PersonCannotLink row."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO project_face_settings
                      (id, project_id, face_recognition_enabled, enable_person_cannot_links)
                    VALUES (1, 1, 0, 0)
                    """
                )
            )

        split_res = self.client.post(
            "/projects/1/people/101/split",
            json={"face_detection_ids": [302], "new_display_name": "拆分无约束"},
        )
        self.assertEqual(split_res.status_code, 200)

        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT COUNT(*) FROM person_cannot_links WHERE project_id = 1")
            ).scalar()
        self.assertEqual(row, 0, "PersonCannotLink must NOT be written when flag is disabled")

    def test_reject_does_not_write_negative_constraint_when_flag_disabled(self) -> None:
        """When enable_negative_constraints=False, rejecting a face must NOT write a constraint."""
        with self._engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO project_face_settings
                      (id, project_id, face_recognition_enabled, enable_negative_constraints)
                    VALUES (1, 1, 0, 0)
                    """
                )
            )

        res = self.client.post("/projects/1/people/101/faces/302/reject")
        self.assertEqual(res.status_code, 200)

        with self._engine.connect() as conn:
            count = conn.execute(
                sa.text("SELECT COUNT(*) FROM face_negative_constraints WHERE project_id = 1")
            ).scalar()
        self.assertEqual(count, 0, "FaceNegativeConstraint must NOT be written when flag is disabled")
