from __future__ import annotations

import os
import tempfile
import unittest

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.query_understanding_service import understand_query  # noqa: E402
from app.services.search.people_query_resolver import resolve_people_query  # noqa: E402
from app.services.search.people_recall import PeopleRecallService  # noqa: E402


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
"""

SEED_SQL = """
INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
VALUES (1, 'Project A', '/tmp/a', '/tmp/a-thumb', 1),
       (2, 'Project B', '/tmp/b', '/tmp/b-thumb', 0);

INSERT INTO persons (
  id, project_id, display_name, normalized_name, is_named, sample_count,
  confirmed_sample_count, auto_assigned_count, review_pending_count, created_by
) VALUES
  (101, 1, '爸爸', '爸爸', 1, 3, 2, 1, 1, 'user'),
  (102, 1, '妈妈 #妈咪 #Mom', '妈妈 #妈咪 #mom', 1, 2, 2, 0, 0, 'user'),
  (201, 2, '爸爸', '爸爸', 1, 1, 1, 0, 0, 'user');

INSERT INTO face_detections (id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, status)
VALUES
  (1001, 1, 11, 10, 10, 20, 20, 'embedded'),
  (1002, 1, 12, 10, 10, 20, 20, 'embedded'),
  (1003, 1, 13, 10, 10, 20, 20, 'embedded'),
  (1004, 1, 14, 10, 10, 20, 20, 'embedded'),
  (1005, 1, 15, 10, 10, 20, 20, 'embedded'),
  (1006, 1, 15, 30, 30, 20, 20, 'embedded'),
  (2001, 2, 21, 10, 10, 20, 20, 'embedded');

INSERT INTO person_face_assignments (
  id, project_id, person_id, face_detection_id, assignment_status,
  assignment_source, confidence, similarity_score, is_positive_sample, is_training_candidate
) VALUES
  (5001, 1, 101, 1001, 'human_confirmed', 'human_label', 0.99, 0.95, 1, 1),
  (5002, 1, 101, 1002, 'review_pending', 'similarity_match', 0.74, 0.69, 0, 1),
  (5003, 1, 102, 1003, 'human_corrected', 'human_label', 0.98, 0.92, 1, 1),
  (5004, 1, 101, 1004, 'auto_assigned', 'similarity_match', 0.83, 0.81, 0, 1),
  (5005, 1, 101, 1005, 'human_confirmed', 'human_label', 0.97, 0.94, 1, 1),
  (5006, 1, 102, 1006, 'human_confirmed', 'human_label', 0.96, 0.93, 1, 1),
  (6001, 2, 201, 2001, 'human_confirmed', 'human_label', 0.99, 0.96, 1, 1);
"""


class PeopleSearchRecallTest(unittest.TestCase):
    def setUp(self) -> None:
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

        self.db: Session = self._SessionLocal()

    def tearDown(self) -> None:
        self.db.close()
        self._engine.dispose()
        if os.path.exists(self._tmp.name):
            os.unlink(self._tmp.name)

    def test_search_father_returns_only_father_photos(self) -> None:
        plan = understand_query("爸爸")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="爸爸",
            query_plan=plan,
        )

        result = PeopleRecallService(self.db, 1).recall(resolution=resolution)
        ids = {c.photo_id for c in result.candidates}

        self.assertEqual(ids, {11, 14, 15})
        self.assertNotIn(12, ids)  # review_pending excluded by default
        self.assertNotIn(21, ids)  # cross-project data must never leak

    def test_search_father_and_mother_requires_same_photo(self) -> None:
        plan = understand_query("爸爸和妈妈")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="爸爸和妈妈",
            query_plan=plan,
        )

        self.assertEqual(resolution.people_filter_mode, "all")
        result = PeopleRecallService(self.db, 1).recall(resolution=resolution)

        ids = {c.photo_id for c in result.candidates}
        self.assertEqual(ids, {15})

    def test_search_person_by_hashtag_alias(self) -> None:
        plan = understand_query("#妈咪")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="#妈咪",
            query_plan=plan,
        )

        self.assertEqual(resolution.matched_person_ids, [102])
        self.assertEqual(resolution.residual_query, "")

        result = PeopleRecallService(self.db, 1).recall(resolution=resolution)
        ids = {c.photo_id for c in result.candidates}
        self.assertEqual(ids, {13, 15})
        self.assertEqual(
            result.candidates[0].people_explain["matched_people"][0]["name_tags"],
            ["妈咪", "Mom"],
        )

    def test_search_person_by_tag_text_without_hash(self) -> None:
        plan = understand_query("mom")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="mom",
            query_plan=plan,
        )

        self.assertEqual(resolution.matched_person_ids, [102])

    def test_search_father_at_seaside_applies_semantic_constraint_after_people(self) -> None:
        plan = understand_query("爸爸在海边")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="爸爸在海边",
            query_plan=plan,
        )

        self.assertEqual(resolution.residual_query, "在海边")

        # Simulate semantic candidate IDs for "海边": photo 13,14.
        result = PeopleRecallService(self.db, 1).recall(
            resolution=resolution,
            constrained_photo_ids={13, 14},
        )

        ids = {c.photo_id for c in result.candidates}
        self.assertEqual(ids, {14})

    def test_project_a_cannot_recall_project_b_people(self) -> None:
        plan = understand_query("爸爸")
        resolution = resolve_people_query(
            self.db,
            project_id=1,
            query="爸爸",
            query_plan=plan,
        )
        result = PeopleRecallService(self.db, 1).recall(resolution=resolution)

        ids = {c.photo_id for c in result.candidates}
        self.assertNotIn(21, ids)


if __name__ == "__main__":
    unittest.main()
