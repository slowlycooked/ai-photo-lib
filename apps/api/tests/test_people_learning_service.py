from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.people_learning_service import (  # noqa: E402
    match_face_detection_to_person,
    rebuild_person_centroid_prototype,
)
from app.services.face_rematch_service import rematch_unknown_faces  # noqa: E402
from app.models.project import Project  # noqa: E402,F401


SCHEMA_SQL = """
CREATE TABLE projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  photo_library_path TEXT NOT NULL,
  thumbnail_path TEXT,
  is_default BOOLEAN NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  deleted_at TEXT
);

CREATE TABLE project_face_settings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL UNIQUE,
  face_recognition_enabled BOOLEAN NOT NULL DEFAULT 1,
  face_provider TEXT NOT NULL DEFAULT 'opencv',
  face_detector_model TEXT NOT NULL DEFAULT 'yunet',
  face_embedding_model TEXT NOT NULL DEFAULT 'sface',
  face_runtime TEXT NOT NULL DEFAULT 'cpu',
  store_face_crops BOOLEAN NOT NULL DEFAULT 1,
  face_crop_storage TEXT NOT NULL DEFAULT 'local',
  auto_accept_threshold REAL NOT NULL DEFAULT 0.75,
  review_threshold REAL NOT NULL DEFAULT 0.45,
  cluster_threshold REAL NOT NULL DEFAULT 0.5,
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

CREATE TABLE face_embeddings (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  face_detection_id INTEGER NOT NULL,
  model_provider TEXT,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT '',
  embedding_dim INTEGER NOT NULL,
  embedding_vector TEXT,
  embedding_hash TEXT,
  embedded_at TEXT,
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

CREATE TABLE person_prototypes (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  person_id INTEGER NOT NULL,
  prototype_type TEXT NOT NULL,
  embedding_vector TEXT,
  sample_count INTEGER NOT NULL DEFAULT 0,
  source_assignment_ids TEXT,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT '',
  embedding_dim INTEGER NOT NULL,
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
"""


def _make_session() -> Session:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = sa.create_engine(f"sqlite:///{tmp.name}", future=True)
    with engine.begin() as conn:
        for statement in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            """
            INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
            VALUES (1, 'Faces', '/tmp/photos', '/tmp/thumbs', 1)
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO project_face_settings (
              id, project_id, face_recognition_enabled, face_embedding_model,
              auto_accept_threshold, review_threshold, min_quality_for_prototype,
              allow_auto_assignment
            ) VALUES (1, 1, 1, 'sface', 0.75, 0.45, 0.70, 1)
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO persons (
              id, project_id, display_name, normalized_name, is_named,
              created_by, sample_count, confirmed_sample_count
            ) VALUES (101, 1, '爸爸', '爸爸', 1, 'user', 1, 1)
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO face_detections (id, project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h, face_quality_score, status)
            VALUES
              (201, 1, 11, 1, 1, 10, 10, 0.90, 'embedded'),
              (202, 1, 12, 2, 2, 10, 10, 0.90, 'embedded'),
              (203, 1, 13, 3, 3, 10, 10, 0.90, 'embedded')
            """
        )
        # Keep the same relative similarities as the previous 3-d fixtures,
        # but in 128 dimensions to match the pgvector schema.
        def _v(first: float, second: float) -> str:
            return json.dumps([first, second] + ([0.0] * 126))

        conn.execute(
            sa.text(
                """
                INSERT INTO face_embeddings (
                  id, project_id, face_detection_id, model_name, model_version, embedding_dim, embedding_vector
                ) VALUES
                  (:id1, 1, 201, 'sface', '', 128, :vec1),
                  (:id2, 1, 202, 'sface', '', 128, :vec2),
                  (:id3, 1, 203, 'sface', '', 128, :vec3)
                """
            ),
            {
                "id1": 301,
                "id2": 302,
                "id3": 303,
                "vec1": _v(1.0, 0.0),
                "vec2": _v(0.95, 0.05),
                "vec3": _v(0.2, 0.2),
            },
        )
        conn.exec_driver_sql(
            """
            INSERT INTO person_face_assignments (
              id, project_id, person_id, face_detection_id,
              assignment_status, assignment_source, is_positive_sample, is_training_candidate
            ) VALUES
              (401, 1, 101, 201, 'human_confirmed', 'human_label', 1, 1)
            """
        )

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def test_rebuild_person_centroid_prototype() -> None:
    db = _make_session()
    try:
        row = rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        assert row is not None
        assert row.prototype_type == "centroid"
        assert row.sample_count == 1
        assert row.embedding_dim == 128
        assert row.embedding_vector == [1.0, 0.0] + ([0.0] * 126)
    finally:
        db.close()


def test_match_face_detection_assigns_auto_and_review() -> None:
    db = _make_session()
    try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)

        auto = match_face_detection_to_person(db, project_id=1, face_detection_id=202)
        assert auto is not None
        assert auto.person_id == 101
        assert auto.assignment_status == "auto_assigned"

        review = match_face_detection_to_person(db, project_id=1, face_detection_id=203)
        assert review is not None
        assert review.person_id == 101
        assert review.assignment_status == "review_pending"

        db.commit()

        rows = db.execute(
            sa.text(
                """
                SELECT assignment_status
                FROM person_face_assignments
                WHERE project_id = 1 AND person_id = 101 AND face_detection_id IN (202, 203)
                ORDER BY face_detection_id
                """
            )
        ).fetchall()
        assert [row[0] for row in rows] == ["auto_assigned", "review_pending"]
    finally:
        db.close()


def test_rematch_unknown_faces_only_matches_unassigned_faces() -> None:
    db = _make_session()
    try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)

        result = rematch_unknown_faces(db, project_id=1, max_faces=10)
        assert result.faces_considered == 2
        assert result.matched_faces == 2
        assert result.auto_assigned == 1
        assert result.review_pending == 1

        db.commit()
        rows = db.execute(
            sa.text(
                """
                SELECT face_detection_id, assignment_status
                FROM person_face_assignments
                WHERE project_id = 1 AND person_id = 101
                ORDER BY face_detection_id
                """
            )
        ).fetchall()
        assert [(row[0], row[1]) for row in rows] == [
            (201, "human_confirmed"),
            (202, "auto_assigned"),
            (203, "review_pending"),
        ]
    finally:
        db.close()


def test_rematch_unknown_faces_supports_person_scope() -> None:
    db = _make_session()
    try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        db.execute(
            sa.text(
                """
                INSERT INTO person_face_assignments (
                  id, project_id, person_id, face_detection_id,
                  assignment_status, assignment_source, is_positive_sample, is_training_candidate
                ) VALUES (402, 1, 101, 202, 'review_pending', 'unknown_cluster', 0, 1)
                """
            )
        )
        db.commit()

        result = rematch_unknown_faces(
            db,
            project_id=1,
            max_faces=10,
            scope="person",
            person_id=101,
        )
        assert result.faces_considered == 1
        assert result.matched_faces == 1
        assert result.auto_assigned == 1
        assert result.review_pending == 0

        row = db.execute(
            sa.text(
                """
                SELECT face_detection_id, assignment_status, assignment_source
                FROM person_face_assignments
                WHERE project_id = 1 AND person_id = 101 AND face_detection_id = 203
                """
            )
        ).first()
        assert row is not None
        assert row[0] == 203
        assert row[1] == "auto_assigned"
        assert row[2] == "targeted_person_rematch"
    finally:
        db.close()


def test_rematch_unknown_faces_supports_time_range_scope() -> None:
    db = _make_session()
    try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        db.execute(
            sa.text(
                """
                UPDATE face_detections
                SET detected_at = CASE
                  WHEN id = 202 THEN '2026-05-28T10:00:00+00:00'
                  WHEN id = 203 THEN '2026-05-10T10:00:00+00:00'
                  ELSE detected_at
                END
                WHERE project_id = 1
                """
            )
        )
        db.commit()

        result = rematch_unknown_faces(
            db,
            project_id=1,
            max_faces=10,
            scope="time_range",
            start_time=datetime.fromisoformat("2026-05-20T00:00:00+00:00"),
            end_time=datetime.fromisoformat("2026-05-30T23:59:59+00:00"),
        )
        assert result.faces_considered == 1
        assert result.matched_faces == 1
    finally:
        db.close()


    # ---------------------------------------------------------------------------
    # New tests for the switches that were previously unconnected
    # ---------------------------------------------------------------------------

    def test_allow_auto_assignment_false_caps_to_review_pending() -> None:
      """When allow_auto_assignment=False, similarity >= auto_accept_threshold must still
      create a review_pending assignment rather than returning None."""
      db = _make_session()
      try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        db.execute(
          sa.text(
            "UPDATE project_face_settings SET allow_auto_assignment = 0 WHERE project_id = 1"
          )
        )
        db.commit()

        # face 202 has high similarity (≥ auto_accept_threshold=0.75) but auto is OFF
        decision = match_face_detection_to_person(db, project_id=1, face_detection_id=202)
        assert decision is not None, "Expected review_pending decision, got None"
        assert decision.assignment_status == "review_pending", (
          f"Expected review_pending, got {decision.assignment_status}"
        )
      finally:
        db.close()


    def test_enable_negative_constraints_false_ignores_existing_negatives() -> None:
      """When enable_negative_constraints=False, negative constraints in the DB must
      not prevent auto-matching."""
      db = _make_session()
      try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        # Write a negative constraint: face 202 is NOT person 101
        db.execute(
          sa.text(
            """
            INSERT INTO face_negative_constraints
              (id, project_id, face_detection_id, not_person_id, source)
            VALUES (901, 1, 202, 101, 'human_rejected')
            """
          )
        )
        db.execute(
          sa.text(
            "UPDATE project_face_settings SET enable_negative_constraints = 0 WHERE project_id = 1"
          )
        )
        db.commit()

        # With the constraint disabled, face 202 should still match person 101
        decision = match_face_detection_to_person(db, project_id=1, face_detection_id=202)
        assert decision is not None, "Expected match even though negative constraint exists when flag is OFF"
        assert decision.person_id == 101
      finally:
        db.close()


    def test_enable_negative_constraints_true_respects_existing_negatives() -> None:
      """When enable_negative_constraints=True (default), existing negative constraints
      must block the matching of the flagged person."""
      db = _make_session()
      try:
        rebuild_person_centroid_prototype(db, project_id=1, person_id=101)
        # Write a negative constraint: face 202 is NOT person 101
        db.execute(
          sa.text(
            """
            INSERT INTO face_negative_constraints
              (id, project_id, face_detection_id, not_person_id, source)
            VALUES (902, 1, 202, 101, 'human_rejected')
            """
          )
        )
        db.commit()

        # With the constraint enabled (default), face 202 should NOT match person 101
        decision = match_face_detection_to_person(db, project_id=1, face_detection_id=202)
        # person 101 is the only candidate — blocked by negative → no match
        assert decision is None, (
          "Expected no match because the only candidate is blocked by a negative constraint"
        )
      finally:
        db.close()
