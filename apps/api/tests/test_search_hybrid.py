from __future__ import annotations

import os
import unittest
from collections import namedtuple
from unittest.mock import patch

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.embedding_client import EmbeddingRequestError  # noqa: E402
from app.services.search_service import (  # noqa: E402
    SearchCandidate,
    _rrf_merge,
    _vector_search,
    search_photos,
)


class _QueryStub:
    def __init__(self, result=None):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _DBStub:
    def __init__(self):
        self.last_sql = None
        self.last_params = None

    def query(self, model):
        return _QueryStub(None)

    def execute(self, sql, params):
        self.last_sql = str(sql)
        self.last_params = params
        Row = namedtuple("Row", ["photo_id", "score"])
        return type("Result", (), {"fetchall": lambda self: [Row(photo_id=11, score=0.88)]})()


class SearchHybridTest(unittest.TestCase):
    def test_rrf_merge_deduplicates_photo_ids(self) -> None:
        keyword = [
            SearchCandidate(photo_id=1, keyword_score=0.9),
            SearchCandidate(photo_id=2, keyword_score=0.8),
        ]
        vector = {2: 0.95, 3: 0.75}

        merged = _rrf_merge(keyword, vector)
        ids = [item.photo_id for item in merged]

        self.assertEqual(sorted(ids), [1, 2, 3])
        self.assertGreater(merged[0].final_score, 0)

    def test_vector_search_uses_project_filter(self) -> None:
        db = _DBStub()
        with patch("app.services.search_service.embed_text", return_value=[0.1] * 1024):
            scores = _vector_search(db, query="cloud hiking", project_id=7, folder_photo_ids=None, limit=5)

        self.assertEqual(scores[11], 0.88)
        self.assertEqual(db.last_params["project_id"], 7)

    def test_hybrid_falls_back_to_keyword_when_vector_fails(self) -> None:
        keyword = [SearchCandidate(photo_id=9, keyword_score=0.7, final_score=0.7)]

        with patch("app.services.search_service._resolve_folder_photo_ids", return_value=None), patch(
            "app.services.search_service._keyword_search", return_value=keyword
        ), patch(
            "app.services.search_service._vector_search",
            side_effect=EmbeddingRequestError("down"),
        ), patch(
            "app.services.search_service._build_result_items",
            return_value=(1, [{"photo_id": 9, "score": 0.7}]),
        ) as build_items:
            total, items = search_photos(
                db=object(),
                query="hike",
                page=1,
                page_size=20,
                project_id=1,
                mode="hybrid",
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["photo_id"], 9)
        self.assertEqual(build_items.call_args.kwargs["mode"], "keyword")


if __name__ == "__main__":
    unittest.main()
