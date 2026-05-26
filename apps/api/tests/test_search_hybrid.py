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
from app.services.query_understanding_service import SearchQueryPlan  # noqa: E402
from app.services.search.people_query_resolver import (  # noqa: E402
    PeopleQueryResolution,
    ResolvedPersonRef,
)
from app.services.search.people_recall import PeopleRecallResult  # noqa: E402
from app.services.search.types import (  # noqa: E402
    EffectiveSearchSettings,
    SearchCandidate,
    VectorMatchScores,
)
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.embedding_client import EmbeddingRequestError  # noqa: E402
from app.services.search.app_service import search_photos  # noqa: E402
from app.services.search.app_service import _core_facet_passes  # noqa: E402
from app.services.search.keyword_recall import _score_result  # noqa: E402


def _default_settings() -> EffectiveSearchSettings:
    return SearchSettingsResolver.defaults()


class RRFMergeTest(unittest.TestCase):
    def test_default_settings_match_project_search_settings_defaults(self) -> None:
        settings = _default_settings()
        self.assertFalse(settings.enable_semantic_tag_boost)

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

    def test_people_stream_participates_in_rrf(self) -> None:
        keyword = [SearchCandidate(photo_id=1, keyword_score=0.8)]
        vector = {2: VectorMatchScores(total_score=0.9)}
        people = [
            SearchCandidate(
                photo_id=3,
                people_score=1.0,
                people_explain={"matched_people": [{"person_id": 101}]},
            )
        ]

        merged = rrf_merge(keyword, vector, _default_settings(), people_results=people)
        ids = {item.photo_id for item in merged}
        self.assertEqual(ids, {1, 2, 3})


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

    def test_query_prefix_is_applied_before_embedding(self) -> None:
        from app.services.search.vector_recall import VectorRecallService

        db = self._make_db_stub()
        settings = _default_settings()
        svc = VectorRecallService(db, settings)

        with patch(
            "app.services.search.vector_recall.resolve_embedding_settings",
            return_value={
                "endpoint_url": "http://127.0.0.1:18083/v1",
                "api_key": "sk-local",
                "model_name": "Qwen3-Embedding-0.6B",
                "embedding_dimension": 1024,
                "timeout_seconds": 30,
                "input_prefix_query": "Represent this search query for retrieving relevant photo descriptions",
            },
        ), patch(
            "app.services.search.vector_recall.embed_text",
            return_value=[0.1] * 1024,
        ) as embed_text_mock, patch(
            "app.services.search.vector_recall._vector_field_search",
            return_value=({}, 0),
        ):
            svc.search(
                query="室内",
                normalized_query="室内 家具",
                semantic_query_text="查找与室内场景相关的照片。重点匹配家具和房间。",
                is_ocr_query=False,
                project_id=7,
                folder_photo_subquery=None,
                limit=5,
            )

        embed_input = embed_text_mock.call_args.args[0]
        assert embed_input.startswith(
            "Represent this search query for retrieving relevant photo descriptions\n"
        )
        assert embed_input.endswith("查找与室内场景相关的照片。重点匹配家具和房间。")

    def test_animal_semantic_query_text_is_preferred_for_embedding(self) -> None:
        from app.services.search.vector_recall import VectorRecallService

        db = self._make_db_stub()
        settings = _default_settings()
        svc = VectorRecallService(db, settings)

        with patch(
            "app.services.search.vector_recall.embed_text",
            return_value=[0.1] * 1024,
        ) as embed_text_mock, patch(
            "app.services.search.vector_recall._vector_field_search",
            return_value=({}, 0),
        ):
            svc.search(
                query="动物",
                normalized_query="动物 猫 狗 鸟",
                semantic_query_text="查找包含动物主体的照片，包括猫、狗、鸟。重点匹配 object_tags。",
                is_ocr_query=False,
                project_id=7,
                folder_photo_subquery=None,
                limit=5,
            )

        self.assertTrue(
            embed_text_mock.call_args.args[0].endswith(
                "查找包含动物主体的照片，包括猫、狗、鸟。重点匹配 object_tags。"
            )
        )

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

    def test_hybrid_people_query_constrains_semantic_and_includes_people_debug(self) -> None:
        people_candidate = SearchCandidate(
            photo_id=2,
            people_score=1.1,
            people_explain={
                "matched_people": [
                    {
                        "person_id": 101,
                        "display_name": "爸爸",
                        "assignment_status": "human_confirmed",
                        "confidence": 0.99,
                        "similarity_score": 0.95,
                        "face_detection_id": 1001,
                    }
                ],
                "people_filter_mode": "any",
            },
        )

        original_plan = SearchQueryPlan(
            original_query="爸爸在海边",
            normalized_query="爸爸在海边",
            exact_terms=["爸爸在海边"],
            metadata_filters={},
        )
        residual_plan = SearchQueryPlan(
            original_query="海边",
            normalized_query="海边",
            exact_terms=["海边"],
            metadata_filters={},
        )

        people_resolution = PeopleQueryResolution(
            query="爸爸在海边",
            residual_query="海边",
            people_filter_mode="any",
            matched_people=[
                ResolvedPersonRef(
                    person_id=101,
                    display_name="爸爸",
                    normalized_name="爸爸",
                    matched_term="爸爸",
                )
            ],
        )

        with (
            patch(
                "app.services.search.app_service.SearchSettingsResolver.resolve",
                return_value=_default_settings(),
            ),
            patch(
                "app.services.search.app_service.understand_query",
                side_effect=[original_plan, residual_plan],
            ),
            patch(
                "app.services.search.app_service.resolve_people_query",
                return_value=people_resolution,
            ),
            patch(
                "app.services.search.app_service.build_folder_photo_ids_subquery",
                return_value=None,
            ),
            patch(
                "app.services.search.app_service.PeopleRecallService.recall",
                return_value=PeopleRecallResult(
                    candidates=[people_candidate],
                    photo_ids={2},
                    matched_person_ids=[101],
                ),
            ),
            patch(
                "app.services.search.app_service.KeywordRecallService.search",
                return_value=[SearchCandidate(photo_id=2, keyword_score=0.8, final_score=0.8)],
            ) as kw_search_mock,
            patch(
                "app.services.search.app_service.VectorRecallService.search",
                return_value=({2: VectorMatchScores(total_score=0.7)}, "test-model", "", 0),
            ),
            patch(
                "app.services.search.app_service.build_result_items",
                return_value=(1, [{"photo_id": 2, "score": 0.1}]),
            ),
        ):
            total, items, debug_payload = search_photos(
                db=MagicMock(),
                query="爸爸在海边",
                page=1,
                page_size=20,
                project_id=1,
                mode="hybrid",
                debug=True,
            )

        self.assertEqual(total, 1)
        self.assertEqual(items[0]["photo_id"], 2)
        kw_kwargs = kw_search_mock.call_args.kwargs
        self.assertEqual(kw_kwargs["constrained_photo_ids"], {2})
        self.assertIsNotNone(debug_payload)
        assert debug_payload is not None
        self.assertIn("people_query_plan", debug_payload)
        self.assertIn("people_candidates", debug_payload)
        self.assertIn("people_filter_mode", debug_payload)
        self.assertEqual(debug_payload.get("matched_person_ids"), [101])


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


class AnimalSearchHeuristicsTest(unittest.TestCase):
    def test_animal_category_query_gets_strong_keyword_floor_for_entity_hit(self) -> None:
        photo = SimpleNamespace(file_name="cat-photo.jpg")
        ai = SimpleNamespace(
            caption="一只猫坐在沙发上",
            ocr_text="",
            scene_tags=["家庭生活"],
            object_tags=["猫", "沙发"],
            activity_tags=[],
            quality_tags=[],
            location_clues=["室内"],
            search_keywords=["猫", "动物", "宠物"],
        )
        plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物 猫 狗 鸟 马 鹿 兔子 鱼 宠物 野生动物 动物园",
            semantic_query_text="查找包含动物主体的照片，包括猫、狗、鸟、马、鹿、兔子、鱼，以及宠物、野生动物。重点匹配 object_tags、search_keywords、caption 中出现动物实体的照片。",
            exact_terms=["动物"],
            expanded_terms=["猫", "狗", "鸟", "马", "鹿", "兔子", "鱼"],
            broad_terms=["宠物", "野生动物", "动物园"],
            intent="animal_search",
        )

        score, _matched, _explain, hit_tiers, term_level_hits = _score_result(
            photo,
            ai,
            plan,
            _default_settings().keyword_field_weights,
        )

        self.assertGreaterEqual(score, 0.65)
        self.assertIn("strong", hit_tiers)
        self.assertIn("猫", term_level_hits["strong"])

    def test_animal_query_requires_entity_evidence(self) -> None:
        candidate = SearchCandidate(
            photo_id=21,
            keyword_score=0.11,
            final_score=0.11,
            evidence_level="A",
            hit_tiers={"exact"},
            keyword_explain={
                "caption": ["动物园"],
                "search_keywords": ["动物园"],
            },
        )
        ai = SimpleNamespace(
            caption="动物园门口的招牌",
            ocr_text="",
            scene_tags=["动物园"],
            object_tags=[],
            activity_tags=[],
            search_keywords=["动物园"],
            location_clues=["户外"],
            raw_result={},
        )
        plan = SimpleNamespace(
            intent="animal_search",
            core_facets=["object"],
            matched_keys=["动物园"],
            exact_terms=["动物园"],
            expanded_terms=["动物", "野生动物"],
            filters={},
        )

        passes, reason = _core_facet_passes(candidate, ai, plan, _default_settings())

        self.assertFalse(passes)
        self.assertEqual(reason, "animal_scene_without_entity")

    def test_animal_query_passes_with_raw_animals_evidence(self) -> None:
        candidate = SearchCandidate(
            photo_id=22,
            keyword_score=0.65,
            final_score=0.65,
            evidence_level="B",
            hit_tiers={"strong"},
            keyword_explain={
                "search_keywords": ["猫", "动物", "宠物"],
            },
        )
        ai = SimpleNamespace(
            caption="一只猫趴在窗台上",
            ocr_text="",
            scene_tags=["家庭生活"],
            object_tags=[],
            activity_tags=[],
            search_keywords=["动物", "宠物"],
            location_clues=["室内"],
            raw_result={"animals": ["猫"]},
        )
        plan = SimpleNamespace(
            intent="animal_search",
            core_facets=["object"],
            matched_keys=["动物"],
            exact_terms=["动物"],
            expanded_terms=["猫", "狗", "鸟"],
            filters={},
        )

        passes, reason = _core_facet_passes(candidate, ai, plan, _default_settings())

        self.assertTrue(passes)
        self.assertEqual(reason, "animal_entity_evidence")


if __name__ == "__main__":
    unittest.main()
