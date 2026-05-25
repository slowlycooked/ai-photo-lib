from __future__ import annotations

import os
import tempfile
from pathlib import Path

import sqlalchemy as sa
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.face.service import (  # noqa: E402
    DetectedFace,
    FaceBoundingBox,
    FaceEmbeddingResult,
)
from app.models import face as face_models  # noqa: F401, E402
from app.models import photo as photo_models  # noqa: F401, E402
from app.models import project as project_models  # noqa: F401, E402
from app.models.face import (  # noqa: E402
    FACE_EMBEDDING_DIMENSION,
    FaceDetection,
    FaceEmbedding,
)
from app.services.face_scan_service import FaceScanService  # noqa: E402


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

CREATE TABLE photos (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_hash TEXT,
  file_size INTEGER,
  mime_type TEXT,
  width INTEGER,
  height INTEGER,
  taken_at TEXT,
  exif TEXT,
  thumbnail_path TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  gps_latitude REAL,
  gps_longitude REAL,
  gps_altitude REAL,
  country_code TEXT,
  country_name TEXT,
  admin1 TEXT,
  admin2 TEXT,
  city TEXT,
  district TEXT,
  formatted_address TEXT,
  location_source TEXT,
  location_resolved_at TEXT,
  camera_make TEXT,
  camera_model TEXT,
  lens_model TEXT,
  focal_length TEXT,
  aperture TEXT,
  exposure_time TEXT,
  iso INTEGER,
  orientation INTEGER,
  folder_id INTEGER,
  relative_path TEXT,
  folder_path TEXT,
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
  status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT,
  detected_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, photo_id, bbox_x, bbox_y, bbox_w, bbox_h)
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
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, face_detection_id, model_name, model_version)
);

CREATE TABLE photo_derivatives (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  path TEXT,
  format TEXT,
  width INTEGER,
  height INTEGER,
  source_path TEXT,
  source_mtime REAL,
  source_hash TEXT,
  quality INTEGER,
  status TEXT NOT NULL DEFAULT 'ready',
  error_message TEXT,
  face_detection_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class FakeFaceProvider:
    def _fake_faces(self) -> list[DetectedFace]:
        return [
            DetectedFace(
                bbox=FaceBoundingBox(10, 12, 60, 60),
                detection_confidence=0.95,
                quality_score=0.88,
                provider_payload={"face": 1},
            ),
            DetectedFace(
                bbox=FaceBoundingBox(55, 18, 48, 48),
                detection_confidence=0.91,
                quality_score=0.81,
                provider_payload={"face": 2},
            ),
        ]

    def _fake_embedding(self, detected_face: DetectedFace) -> FaceEmbeddingResult:
        x = float(detected_face.bbox.x)
        vector = [x, x + 1.0, x + 2.0] + [0.0] * (FACE_EMBEDDING_DIMENSION - 3)
        return FaceEmbeddingResult(
            vector=vector,
            embedding_dim=FACE_EMBEDDING_DIMENSION,
            model_provider="fake",
            model_name="fake-sface",
            model_version="v1",
        )

    def detect_faces(self, image_path: Path) -> list[DetectedFace]:
        return self._fake_faces()

    def detect_faces_from_bgr(self, image_bgr) -> list[DetectedFace]:
        return self._fake_faces()

    def embed_face(self, image_path: Path, detected_face: DetectedFace) -> FaceEmbeddingResult:
        return self._fake_embedding(detected_face)

    def embed_face_from_bgr(self, image_bgr, detected_face: DetectedFace) -> FaceEmbeddingResult:
        return self._fake_embedding(detected_face)


class DriftedFaceProvider(FakeFaceProvider):
    def _fake_faces(self) -> list[DetectedFace]:
        return [
            DetectedFace(
                bbox=FaceBoundingBox(12, 14, 60, 60),
                detection_confidence=0.95,
                quality_score=0.88,
                provider_payload={"face": 1},
            ),
            DetectedFace(
                bbox=FaceBoundingBox(57, 20, 48, 48),
                detection_confidence=0.91,
                quality_score=0.81,
                provider_payload={"face": 2},
            ),
        ]


class FarShiftFaceProvider(FakeFaceProvider):
    def _fake_faces(self) -> list[DetectedFace]:
        return [
            DetectedFace(
                bbox=FaceBoundingBox(75, 20, 40, 40),
                detection_confidence=0.90,
                quality_score=0.7,
                provider_payload={"face": 99},
            ),
        ]


def _make_session() -> tuple[Session, Path]:
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    image_dir = Path(tempfile.mkdtemp())
    image_path = image_dir / "group.jpg"
    Image.new("RGB", (120, 90), color=(180, 170, 160)).save(image_path)

    thumb_dir = image_dir / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    engine = sa.create_engine(f"sqlite:///{tmp_db.name}", future=True)
    with engine.begin() as conn:
        for statement in [part.strip() for part in SCHEMA_SQL.split(";") if part.strip()]:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            f"""
            INSERT INTO projects (id, name, photo_library_path, thumbnail_path, is_default)
            VALUES (1, 'Faces', '{image_dir}', '{thumb_dir}', 1)
            """
        )
        conn.exec_driver_sql(
            f"""
            INSERT INTO photos (id, project_id, file_path, file_name, width, height, mime_type, status)
            VALUES (101, 1, '{image_path}', 'group.jpg', 120, 90, 'image/jpeg', 'indexed')
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO project_face_settings (
              id, project_id, face_recognition_enabled, face_provider,
              face_detector_model, face_embedding_model, store_face_crops
            ) VALUES (1, 1, 1, 'opencv', 'yunet', 'sface', 1)
            """
        )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal(), image_dir


def test_face_scan_service_persists_detections_embeddings_and_crops() -> None:
    db, temp_dir = _make_session()
    try:
        service = FaceScanService(db)
        result = service.scan_photo(1, 101, provider=FakeFaceProvider())

        assert result.faces_detected == 2
        assert result.detections_created == 2
        assert result.embeddings_created == 2
        assert result.failures == 0

        detections = db.query(FaceDetection).filter(FaceDetection.project_id == 1).all()
        embeddings = db.query(FaceEmbedding).filter(FaceEmbedding.project_id == 1).all()
        assert len(detections) == 2
        assert len(embeddings) == 2
        assert all(face.status == "embedded" for face in detections)
        assert all(face.face_crop_path for face in detections)
        assert all(Path(face.face_crop_path).exists() for face in detections if face.face_crop_path)
    finally:
        db.close()
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.unlink(Path(root) / name)
            for name in dirs:
                os.rmdir(Path(root) / name)
        os.rmdir(temp_dir)


def test_face_scan_service_respects_project_min_face_size_and_crop_setting() -> None:
    db, temp_dir = _make_session()
    try:
        db.execute(
            sa.text(
                """
                UPDATE project_face_settings
                SET store_face_crops = 0,
                    min_face_size = 100
                WHERE project_id = 1
                """
            )
        )
        db.commit()

        service = FaceScanService(db)
        result = service.scan_photo(1, 101, provider=FakeFaceProvider())

        assert result.faces_detected == 2
        assert result.detections_created == 2
        assert result.embeddings_created == 0
        assert result.embeddings_updated == 0
        assert result.failures == 0

        detections = db.query(FaceDetection).filter(FaceDetection.project_id == 1).all()
        assert len(detections) == 2
        assert all(face.status == "too_small_for_recognition" for face in detections)
        assert all(face.face_crop_path is None for face in detections)
        assert all(face.face_crop_hash is None for face in detections)
    finally:
        db.close()
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.unlink(Path(root) / name)
            for name in dirs:
                os.rmdir(Path(root) / name)
        os.rmdir(temp_dir)


def test_face_scan_service_is_idempotent_for_same_bboxes() -> None:
    db, temp_dir = _make_session()
    try:
        service = FaceScanService(db)
        first = service.scan_photo(1, 101, provider=FakeFaceProvider())
        second = service.scan_photo(1, 101, provider=FakeFaceProvider())

        assert first.detections_created == 2
        assert second.detections_created == 0
        assert second.detections_updated == 2
        assert second.embeddings_created == 0
        assert second.embeddings_updated == 2
        assert db.query(FaceDetection).count() == 2
        assert db.query(FaceEmbedding).count() == 2
    finally:
        db.close()
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.unlink(Path(root) / name)
            for name in dirs:
                os.rmdir(Path(root) / name)
        os.rmdir(temp_dir)


def test_face_scan_service_reuses_detection_ids_when_bbox_drift_has_high_iou() -> None:
    db, temp_dir = _make_session()
    try:
        service = FaceScanService(db)
        first = service.scan_photo(1, 101, provider=FakeFaceProvider())
        assert first.detections_created == 2

        before_ids = {
            row[0]
            for row in db.execute(
                sa.text(
                    """
                    SELECT id FROM face_detections
                    WHERE project_id = 1
                    ORDER BY id ASC
                    """
                )
            ).fetchall()
        }

        second = service.scan_photo(1, 101, provider=DriftedFaceProvider())
        assert second.detections_created == 0
        assert second.detections_updated == 2

        after_ids = {
            row[0]
            for row in db.execute(
                sa.text(
                    """
                    SELECT id FROM face_detections
                    WHERE project_id = 1
                    ORDER BY id ASC
                    """
                )
            ).fetchall()
        }

        assert after_ids == before_ids
        assert db.query(FaceDetection).count() == 2
    finally:
        db.close()
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.unlink(Path(root) / name)
            for name in dirs:
                os.rmdir(Path(root) / name)
        os.rmdir(temp_dir)


def test_face_scan_service_marks_unmatched_old_detections_as_disappeared() -> None:
    db, temp_dir = _make_session()
    try:
        service = FaceScanService(db)
        first = service.scan_photo(1, 101, provider=FakeFaceProvider())
        assert first.detections_created == 2

        second = service.scan_photo(1, 101, provider=FarShiftFaceProvider())
        assert second.detections_created == 1

        rows = db.execute(
            sa.text(
                """
                SELECT status, COUNT(*)
                FROM face_detections
                WHERE project_id = 1
                GROUP BY status
                ORDER BY status
                """
            )
        ).fetchall()
        status_counts = {row[0]: row[1] for row in rows}
        assert status_counts.get("embedded", 0) == 1
        assert status_counts.get("disappeared", 0) == 2
    finally:
        db.close()
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.unlink(Path(root) / name)
            for name in dirs:
                os.rmdir(Path(root) / name)
        os.rmdir(temp_dir)
