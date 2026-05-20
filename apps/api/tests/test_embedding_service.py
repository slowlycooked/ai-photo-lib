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
    build_embedding_inputs,
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


class EmbeddingServiceTest(unittest.TestCase):
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
        )
        db = _FakeDB()

        with patch("app.services.embedding_service.embed_texts", return_value=[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]):
            row = upsert_photo_embeddings(db, project_id=1, photo_id=10, ai=ai, model_name="embed-model")
            self.assertEqual(db.add_calls, 1)
            self.assertEqual(row.project_id, 1)
            self.assertEqual(row.photo_id, 10)
            self.assertEqual(row.embedding_model, "embed-model")

            row2 = upsert_photo_embeddings(db, project_id=1, photo_id=10, ai=ai, model_name="embed-model")
            self.assertEqual(db.add_calls, 1)
            self.assertIs(row2, row)


if __name__ == "__main__":
    unittest.main()
