from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.models.ai import PhotoEmbedding  # noqa: E402
from app.services.embedding_service import (  # noqa: E402
    EMBEDDING_INPUT_VERSION,
    _REQUIRED_PHOTO_EMBEDDING_COLUMNS,
    build_embedding_inputs,
    build_photo_embedding_document,
    is_embedding_stale,
    upsert_photo_embeddings,
)


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.add_calls = 0

    def query(self, model):
        return _FakeQuery(self.row)

    def add(self, obj):
        self.add_calls += 1
        if isinstance(obj, PhotoEmbedding):
            self.row = obj


class _FakeSchemaDB:
    def __init__(self):
        self.query_called = False

    def get_bind(self):
        return object()

    def query(self, model):
        self.query_called = True
        raise AssertionError("query should not be called for incompatible schema")


class _FakeInspector:
    def __init__(self, columns):
        self._columns = columns

    def get_columns(self, table_name):
        if table_name != "photo_embeddings":
            raise AssertionError(f"unexpected table_name: {table_name}")
        return [{"name": name} for name in self._columns]


class EmbeddingServiceTest(unittest.TestCase):
    def test_required_photo_embeddings_columns_match_model_contract(self) -> None:
        expected_columns = {
            "id",
            "project_id",
            "photo_id",
            "caption_embedding",
            "tag_embedding",
            "ocr_embedding",
            "content_embedding",
            "caption_text_hash",
            "tag_text_hash",
            "ocr_text_hash",
            "content_text_hash",
            "embedding_input_version",
            "embedding_model",
            "embedding_dimension",
            "embedding_status",
            "embedding_error",
            "embedded_at",
            "updated_at",
        }

        self.assertSetEqual(_REQUIRED_PHOTO_EMBEDDING_COLUMNS, expected_columns)

    def test_build_embedding_inputs_merges_and_dedups_tags(self) -> None:
        ai = SimpleNamespace(
            caption="  mountain trail  ",
            ocr_text="  receipt total  ",
            scene_tags=["mountain", "sunrise"],
            object_tags=["backpack", "mountain"],
            activity_tags=["hiking"],
            quality_tags=["sharp"],
            location_clues=["cloud sea"],
            search_keywords=["hike", "sunrise"],
            people_count=0,
            confidence=1.0,
        )

        inputs = build_embedding_inputs(ai)

        self.assertEqual(inputs["caption"], "mountain trail")
        self.assertEqual(inputs["ocr"], "receipt total")
        self.assertEqual(
            inputs["tags"],
            "mountain;sunrise;backpack;hiking;sharp;cloud sea;hike",
        )

    def test_upsert_photo_embeddings_insert_then_update(self) -> None:
        ai = SimpleNamespace(
            caption="cat",
            ocr_text="invoice",
            scene_tags=["home"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=["pet"],
            people_count=0,
            confidence=1.0,
        )
        db = _FakeDB()

        with patch("app.services.embedding_service.embed_texts", return_value=[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024, [0.4] * 1024]):
            row = upsert_photo_embeddings(db, project_id=1, photo_id=10, ai=ai, model_name="embed-model")
            self.assertEqual(db.add_calls, 1)
            self.assertEqual(row.project_id, 1)
            self.assertEqual(row.photo_id, 10)
            self.assertEqual(row.embedding_model, "embed-model")

            row2 = upsert_photo_embeddings(db, project_id=1, photo_id=10, ai=ai, model_name="embed-model")
            self.assertEqual(db.add_calls, 1)
            self.assertIs(row2, row)

    def test_is_embedding_stale_true_when_text_hash_changes(self) -> None:
        ai = SimpleNamespace(
            caption="cat",
            ocr_text="invoice",
            scene_tags=["home"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=["pet"],
            people_count=0,
            confidence=1.0,
        )
        embedding = SimpleNamespace(
            embedding_status="ready",
            embedding_model="embed-model",
            embedding_dimension=1024,
            caption_text_hash="x",
            tag_text_hash="y",
            ocr_text_hash="z",
        )
        self.assertTrue(is_embedding_stale(ai, embedding, model_name="embed-model", dimension=1024))

    def test_is_embedding_stale_true_when_model_changes(self) -> None:
        ai = SimpleNamespace(
            caption="cat",
            ocr_text="invoice",
            scene_tags=["home"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=["pet"],
            people_count=0,
            confidence=1.0,
        )
        with patch("app.services.embedding_service._hash_text", side_effect=["h1", "h2", "h3"]):
            embedding = SimpleNamespace(
                embedding_status="ready",
                embedding_model="old-model",
                embedding_dimension=1024,
                caption_text_hash="h1",
                tag_text_hash="h2",
                ocr_text_hash="h3",
            )
            self.assertTrue(is_embedding_stale(ai, embedding, model_name="new-model", dimension=1024))

    def test_upsert_photo_embeddings_old_schema_raises_runtime_error(self) -> None:
        ai = SimpleNamespace(
            caption="cat",
            ocr_text="invoice",
            scene_tags=["home"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=["pet"],
            people_count=0,
            confidence=1.0,
        )
        old_schema_columns = {
            "photo_id",
            "caption_embedding",
            "tag_embedding",
            "ocr_embedding",
            "updated_at",
        }
        db = _FakeSchemaDB()

        with patch(
            "app.services.embedding_service.inspect",
            return_value=_FakeInspector(old_schema_columns),
        ):
            with self.assertRaises(RuntimeError) as cm:
                upsert_photo_embeddings(db, project_id=1, photo_id=10, ai=ai, model_name="embed-model")

        self.assertIn("Incompatible table schema", str(cm.exception))
        self.assertIn("alembic upgrade head", str(cm.exception))
        self.assertFalse(db.query_called)

    # ── content embedding / version tests ────────────────────────────────────

    def test_build_photo_embedding_document_returns_string(self) -> None:
        ai = SimpleNamespace(
            caption="mountain view",
            ocr_text="",
            scene_tags=["mountain", "sunrise"],
            object_tags=["backpack"],
            activity_tags=["hiking"],
            quality_tags=[],
            location_clues=[],
            search_keywords=["hike"],
            people_count=0,
            confidence=1.0,
        )
        doc = build_photo_embedding_document(ai)
        self.assertIsInstance(doc, str)
        self.assertIn("mountain view", doc)
        self.assertIn("hiking", doc)

    def test_build_photo_embedding_document_accepts_photo(self) -> None:
        ai = SimpleNamespace(
            caption="indoor office",
            ocr_text="",
            scene_tags=[],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=[],
            people_count=0,
            confidence=1.0,
        )
        photo = SimpleNamespace(file_name="IMG_001.jpg", taken_at=None, relative_path=None, file_path=None)
        doc = build_photo_embedding_document(ai, photo=photo)
        self.assertIn("IMG_001.jpg", doc)

    def test_is_embedding_stale_true_when_content_hash_missing(self) -> None:
        """Embeddings generated before content_text_hash existed are stale."""
        ai = SimpleNamespace(
            caption="beach",
            ocr_text="",
            scene_tags=[],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=[],
            people_count=0,
            confidence=1.0,
        )
        embedding = SimpleNamespace(
            embedding_status="ready",
            embedding_model="embed-model",
            embedding_dimension=1024,
            caption_text_hash=None,
            tag_text_hash=None,
            ocr_text_hash=None,
            # content_text_hash absent entirely (old row)
        )
        self.assertTrue(is_embedding_stale(ai, embedding, model_name="embed-model", dimension=1024))

    def test_is_embedding_stale_true_when_input_version_changes(self) -> None:
        """Embeddings with a different input_version are stale."""
        ai = SimpleNamespace(
            caption="beach",
            ocr_text="",
            scene_tags=[],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=[],
            people_count=0,
            confidence=1.0,
        )
        # Simulate row written with an old input version
        embedding = SimpleNamespace(
            embedding_status="ready",
            embedding_model="embed-model",
            embedding_dimension=1024,
            caption_text_hash=None,
            tag_text_hash=None,
            ocr_text_hash=None,
            content_text_hash=None,
            embedding_input_version="photo_semantic_v0",  # outdated
        )
        self.assertTrue(
            is_embedding_stale(ai, embedding, model_name="embed-model", dimension=1024),
        )

    def test_embedding_input_version_constant_not_empty(self) -> None:
        self.assertIsInstance(EMBEDDING_INPUT_VERSION, str)
        self.assertGreater(len(EMBEDDING_INPUT_VERSION), 0)

    def test_two_projects_embedding_inputs_are_independent(self) -> None:
        """build_embedding_inputs must be stateless and project-neutral."""
        ai_a = SimpleNamespace(
            caption="architecture",
            ocr_text="",
            scene_tags=["building"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=[],
            people_count=0,
            confidence=1.0,
        )
        ai_b = SimpleNamespace(
            caption="family dinner",
            ocr_text="",
            scene_tags=["home"],
            object_tags=[],
            activity_tags=[],
            quality_tags=[],
            location_clues=[],
            search_keywords=[],
            people_count=2,
            confidence=1.0,
        )
        inputs_a = build_embedding_inputs(ai_a)
        inputs_b = build_embedding_inputs(ai_b)
        self.assertNotEqual(inputs_a["caption"], inputs_b["caption"])
        self.assertNotIn("building", inputs_b["tags"])
        self.assertNotIn("home", inputs_a["tags"])


if __name__ == "__main__":
    unittest.main()
