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
    VectorMatchScores,
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
        Row = namedtuple("Row", ["photo_id", "similarity"])
        return type("Result", (), {"fetchall": lambda self: [Row(photo_id=11, similarity=0.88)]})()


class SearchHybridTest(unittest.TestCase):
    def test_rrf_merge_deduplicates_photo_ids(self) -> None:
        keyword = [
            SearchCandidate(photo_id=1, keyword_score=0.9),
            SearchCandidate(photo_id=2, keyword_score=0.8),
        ]
        vector = {
            2: VectorMatchScores(total_score=0.95),
            3: VectorMatchScores(total_score=0.75),
        }

        merged = _rrf_merge(keyword, vector)
        ids = [item.photo_id for item in merged]

        self.assertEqual(sorted(ids), [1, 2, 3])
        self.assertGreater(merged[0].final_score, 0)

    def test_vector_search_uses_project_filter(self) -> None:
        db = _DBStub()
        with patch("app.services.search_service.embed_text", return_value=[0.1] * 1024):
            with patch("app.services.search_service._vector_field_search") as field_search:
                field_search.side_effect = [
                    {11: 0.9},
                    {11: 0.85},
                    {11: 0.2},
                ]
                scores = _vector_search(db, query="cloud hiking", project_id=7, folder_photo_ids=None, limit=5)

        self.assertIsInstance(scores[11], VectorMatchScores)
        self.assertGreater(scores[11].total_score, 0.0)

    def test_vector_search_filters_low_similarity_results(self) -> None:
        db = _DBStub()
        with patch("app.services.search_service.embed_text", return_value=[0.1] * 1024):
            with patch("app.services.search_service._vector_field_search") as field_search:
                field_search.side_effect = [
                    {11: 0.1},
                    {11: 0.1},
                    {11: 0.1},
                ]
                scores = _vector_search(db, query="weak", project_id=7, folder_photo_ids=None, limit=5)

        self.assertEqual(scores, {})

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

    def test_debug_false_keeps_old_shape_compatible(self) -> None:
        candidate = SearchCandidate(photo_id=1, keyword_score=0.4, final_score=0.4)
        with patch("app.services.search_service._resolve_folder_photo_ids", return_value=None), patch(
            "app.services.search_service._keyword_search", return_value=[candidate]
        ), patch(
            "app.services.search_service._build_result_items",
            return_value=(1, [{"photo_id": 1, "score": 0.4}]),
        ) as build_items:
            search_photos(
                db=object(),
                query="cat",
                project_id=1,
                mode="keyword",
                debug=False,
            )

        self.assertFalse(build_items.call_args.kwargs["debug"])

    def test_debug_true_returns_score_details(self) -> None:
        candidate = SearchCandidate(
            photo_id=1,
            keyword_score=0.5,
            vector_score=0.6,
            rrf_score=0.07,
            final_score=0.07,
            match_source=["keyword", "vector_tag"],
        )
        item = {
            "photo_id": 1,
            "file_name": "a.jpg",
            "thumbnail_url": "/api/photos/1/thumbnail",
            "updated_at": None,
            "taken_at": None,
            "width": None,
            "height": None,
            "caption": "x",
            "matched_tags": [],
            "score": 0.07,
            "keyword_score": 0.5,
            "vector_score": 0.6,
            "rrf_score": 0.07,
            "match_source": ["keyword", "vector_tag"],
        }
        with patch("app.services.search_service._resolve_folder_photo_ids", return_value=None), patch(
            "app.services.search_service._keyword_search", return_value=[candidate]
        ), patch(
            "app.services.search_service._build_result_items",
            return_value=(1, [item]),
        ):
            total, items = search_photos(
                db=object(),
                query="cat",
                project_id=1,
                mode="keyword",
                debug=True,
            )

        self.assertEqual(total, 1)
        self.assertIn("keyword_score", items[0])
        self.assertIn("match_source", items[0])


if __name__ == "__main__":
    unittest.main()
