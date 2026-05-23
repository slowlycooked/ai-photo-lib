from __future__ import annotations

import os
import unittest
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Required before importing app.config.Settings at module import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.search.fusion import rrf_merge  # noqa: E402
from app.services.search.types import (  # noqa: E402
    EffectiveSearchSettings,
    SearchCandidate,
    VectorMatchScores,
)
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.embedding_client import EmbeddingRequestError  # noqa: E402
from app.services.search.app_service import search_photos  # noqa: E402
from app.services.search.app_service import _core_facet_passes  # noqa: E402


def _default_settings() -> EffectiveSearchSettings:
    return SearchSettingsResolver.defaults()


class RRFMergeTest(unittest.TestCase):
    def test_deduplicates_photo_ids(self) -> None:
        keyword = [
            SearchCandidate(photo_id=1, keyword_score=0.9),
            SearchCandidate(photo_id=2, keyword_score=0.8),
        ]
        vector = {
            2: VectorMatchScores(total_score=0.95),
            3: VectorMatchScores(total_score=0.75),
        }

        merged = rrf_merge(keyword, vector, _default_settings())
        ids = [item.photo_id for item in merged]

        self.assertEqual(sorted(ids), [1, 2, 3])
        self.assertGreater(merged[0].final_score, 0)

    def test_empty_keyword_returns_vector_only(self) -> None:
        vector = {5: VectorMatchScores(total_score=0.8)}
        merged = rrf_merge([], vector, _default_settings())
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].photo_id, 5)

    def test_empty_vector_returns_keyword_only(self) -> None:
        keyword = [SearchCandidate(photo_id=7, keyword_score=0.6)]
        merged = rrf_merge(keyword, {}, _default_settings())
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].photo_id, 7)

    def test_both_empty_returns_empty(self) -> None:
        merged = rrf_merge([], {}, _default_settings())
        self.assertEqual(merged, [])


class VectorRecallServiceTest(unittest.TestCase):
    def _make_db_stub(self, photo_id: int = 11, similarity: float = 0.88):
        Row = namedtuple("Row", ["photo_id", "similarity"])
        rows = [Row(photo_id=photo_id, similarity=similarity)]

        db = MagicMock()
        result = MagicMock()
        result.fetchall.return_value = rows
        result.scalar.return_value = 0
        db.execute.return_value = result
        db.query.return_value.filter.return_value.first.return_value = None
        return db

    def test_uses_project_filter(self) -> None:
        from app.services.search.vector_recall import VectorRecallService

        db = self._make_db_stub()
        settings = _default_settings()
        svc = VectorRecallService(db, settings)

        with patch(
            "app.services.search.vector_recall.embed_text",
            return_value=[0.1] * 1024,
        ), patch(
            "app.services.search.vector_recall._vector_field_search",
            return_value=({11: 0.9}, 0),
        ) as field_search:
            scores, _model, _reason, _stale = svc.search(
                query="cloud hiking",
                normalized_query="cloud hiking",
                is_ocr_query=False,
                project_id=7,
                folder_photo_subquery=None,
                limit=5,
            )

        self.assertIsInstance(scores.get(11), VectorMatchScores)

    def test_filters_low_similarity_results(self) -> None:
        from app.services.search.vector_recall import VectorRecallService

        db = self._make_db_stub()
        settings = _default_settings()
        svc = VectorRecallService(db, settings)

        with patch(
            "app.services.search.vector_recall.embed_text",
            return_value=[0.1] * 1024,
        ), patch(
            "app.services.search.vector_recall._vector_field_search",
            return_value=({11: 0.01}, 0),
        ):
            scores, _m, _r, _stale = svc.search(
                query="weak",
                normalized_query="weak",
                is_ocr_query=False,
                project_id=7,
                folder_photo_subquery=None,
                limit=5,
            )

        # 0.01 is well below default vector_min_score; should be filtered out
        self.assertEqual(scores, {})


class SearchPhotosTest(unittest.TestCase):
    """Integration-style tests for app_service.search_photos fallback/debug."""

    def _make_candidate(self, photo_id: int = 9, score: float = 0.7) -> SearchCandidate:
        return SearchCandidate(photo_id=photo_id, keyword_score=score, final_score=score)

    def test_hybrid_falls_back_to_keyword_when_vector_fails(self) -> None:
        candidate = self._make_candidate()

        with (
            patch(
                "app.services.search.app_service.SearchSettingsResolver.resolve",
                return_value=_default_settings(),
            ),
            patch(
                "app.services.search.app_service.understand_query",
                return_value=MagicMock(
                    structured_filters={},
                    expanded_terms=[],
                    support_terms=[],
                    broad_terms=[],
                    dominant_intent="general",
                    query_type="general",
                    is_ocr_query=False,
                    semantic_tag_boost=False,
                ),
            ),
            patch(
                "app.services.search.app_service.build_folder_photo_ids_subquery",
                return_value=None,
            ),
            patch(
                "app.services.search.app_service.KeywordRecallService.search",
                return_value=[candidate],
            ),
            patch(
                "app.services.search.app_service.VectorRecallService.search",
                side_effect=EmbeddingRequestError("down"),
            ),
            patch(
                "app.services.search.app_service.build_result_items",
                return_value=(1, [{"photo_id": 9, "score": 0.7}]),
            ) as build_items,
        ):
            total, items, _debug = search_photos(
                db=MagicMock(),
                query="hike",
                page=1,
                page_size=20,
                project_id=1,
                mode="hybrid",
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["photo_id"], 9)

    def test_debug_true_returns_debug_payload(self) -> None:
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
        with (
            patch(
                "app.services.search.app_service.SearchSettingsResolver.resolve",
                return_value=_default_settings(),
            ),
            patch(
                "app.services.search.app_service.understand_query",
                return_value=MagicMock(
                    structured_filters={},
                    expanded_terms=[],
                    support_terms=[],
                    broad_terms=[],
                    dominant_intent="general",
                    query_type="general",
                    is_ocr_query=False,
                    semantic_tag_boost=False,
                ),
            ),
            patch(
                "app.services.search.app_service.build_folder_photo_ids_subquery",
                return_value=None,
            ),
            patch(
                "app.services.search.app_service.KeywordRecallService.search",
                return_value=[candidate],
            ),
            patch(
                "app.services.search.app_service.VectorRecallService.search",
                return_value=({}, "test-model", "ok", 0),
            ),
            patch(
                "app.services.search.app_service.build_result_items",
                return_value=(1, [item]),
            ),
        ):
            total, items, debug_payload = search_photos(
                db=MagicMock(),
                query="cat",
                project_id=1,
                mode="keyword",
                debug=True,
            )

        self.assertEqual(total, 1)
        self.assertIn("keyword_score", items[0])
        self.assertIn("match_source", items[0])


class CoreFacetIndoorTest(unittest.TestCase):
    def test_indoor_query_filters_weak_location_only_match(self) -> None:
        candidate = SearchCandidate(
            photo_id=6,
            keyword_score=0.0414,
            final_score=0.0414,
            evidence_level="A",
            hit_tiers={"exact"},
            keyword_explain={
                "search_keywords": ["室内"],
                "location_clues": ["室内"],
            },
        )
        ai = SimpleNamespace(
            caption="老旧建筑中的窗户和窗幔",
            ocr_text="",
            scene_tags=[],
            object_tags=["窗户", "窗幔"],
            activity_tags=[],
            search_keywords=["室内"],
            location_clues=["室内"],
        )
        plan = SimpleNamespace(
            core_facets=["scene"],
            matched_keys=["室内"],
            exact_terms=["室内"],
            filters={"indoor_outdoor": "indoor"},
        )

        passes, reason = _core_facet_passes(candidate, ai, plan, _default_settings())

        self.assertFalse(passes)
        self.assertEqual(reason, "indoor_weak_tag_only")

    def test_indoor_query_keeps_rich_visual_match(self) -> None:
        candidate = SearchCandidate(
            photo_id=13,
            keyword_score=0.1924,
            final_score=0.1924,
            evidence_level="A",
            hit_tiers={"exact", "strong"},
            keyword_explain={
                "caption": ["室内"],
                "object_tags": ["家具"],
                "search_keywords": ["室内"],
            },
        )
        ai = SimpleNamespace(
            caption="一只猫坐在家具上，看起来像是在室内",
            ocr_text="",
            scene_tags=[],
            object_tags=["家具"],
            activity_tags=[],
            search_keywords=["室内", "家庭生活"],
            location_clues=["室内"],
        )
        plan = SimpleNamespace(
            core_facets=["scene"],
            matched_keys=["室内"],
            exact_terms=["室内"],
            filters={"indoor_outdoor": "indoor"},
        )

        passes, reason = _core_facet_passes(candidate, ai, plan, _default_settings())

        self.assertTrue(passes)
        self.assertEqual(reason, "indoor_positive_visual_evidence")


if __name__ == "__main__":
    unittest.main()
