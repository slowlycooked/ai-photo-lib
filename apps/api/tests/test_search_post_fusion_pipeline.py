from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.query_understanding_service import SearchQueryPlan  # noqa: E402
from app.services.search.post_fusion_pipeline import apply_post_fusion_pipeline  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.search.types import SearchCandidate  # noqa: E402


class PostFusionPipelineTest(unittest.TestCase):
    def test_evidence_filter_removes_low_confidence_candidates(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            enable_semantic_tag_boost=False,
        )
        plan = SearchQueryPlan(
            original_query="测试",
            normalized_query="测试",
            exact_terms=["测试"],
            intent="semantic_photo_search",
            core_facets=[],
        )
        candidates = [
            SearchCandidate(photo_id=1, final_score=0.3, rrf_score=0.3, hit_tiers={"exact"}),
            SearchCandidate(photo_id=2, final_score=0.2, rrf_score=0.2, vector_score=0.1),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [1])
        self.assertEqual(result.filtered_count, 1)
        self.assertEqual(result.filtered_out[0].photo_id, 2)
        self.assertEqual(result.trace_events[0]["stage"], "evidence_filter")

    def test_semantic_boost_stage_is_recorded_when_enabled(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=False,
            enable_semantic_tag_boost=True,
        )
        plan = SearchQueryPlan(
            original_query="室内",
            normalized_query="室内",
            exact_terms=["室内"],
            intent="semantic_photo_search",
            core_facets=[],
            penalize_tags=["室外"],
        )
        candidates = [SearchCandidate(photo_id=3, final_score=0.4, rrf_score=0.4, hit_tiers={"exact"})]

        with patch(
            "app.services.search.post_fusion_pipeline.apply_semantic_tag_boost",
            return_value=candidates,
        ) as semantic_boost:
            result = apply_post_fusion_pipeline(
                db=MagicMock(),
                candidates=candidates,
                query_plan=plan,
                settings=settings,
                project_id=1,
            )

        semantic_boost.assert_called_once()
        self.assertTrue(any(evt["stage"] == "semantic_tag_boost" for evt in result.trace_events))

    def test_query_constraints_raise_min_display_level(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            enable_semantic_tag_boost=False,
        )
        plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物",
            exact_terms=["动物"],
            intent="animal_search",
            core_facets=[],
            query_constraints={
                "requires_visual_evidence": True,
                "allow_weak_only_match": False,
                "min_evidence_level": "high",
                "query_core_facets": ["object"],
            },
        )
        candidates = [
            SearchCandidate(photo_id=1, final_score=0.4, rrf_score=0.4, hit_tiers={"exact"}),
            SearchCandidate(photo_id=2, final_score=0.3, rrf_score=0.3, hit_tiers={"strong"}),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [1])
        self.assertEqual(result.trace_events[0]["min_display_level"], "A")

    def test_query_constraints_reject_vector_only_c_when_weak_match_disallowed(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            enable_semantic_tag_boost=False,
            vector_strict_score=0.4,
            entity_object_vector_only_min_score=0.0,
            entity_object_tag_min_score=0.0,
            entity_object_caption_min_score=0.0,
        )
        plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物",
            exact_terms=["动物"],
            intent="animal_search",
            core_facets=[],
            query_constraints={
                "requires_visual_evidence": True,
                "allow_weak_only_match": False,
                "min_evidence_level": "C",
                "query_core_facets": ["object"],
            },
        )
        candidates = [
            SearchCandidate(photo_id=1, final_score=0.4, rrf_score=0.4, vector_score=0.5, keyword_score=0.0),
            SearchCandidate(photo_id=2, final_score=0.5, rrf_score=0.5, hit_tiers={"exact"}, keyword_score=1.0),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [2])
        self.assertTrue(any(c.filter_reason == "query_constraints:no_vector_only_weak_match" for c in result.filtered_out))

    def test_query_constraints_allow_strict_vector_only_match_when_enabled(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            enable_semantic_tag_boost=False,
            vector_strict_score=0.4,
        )
        plan = SearchQueryPlan(
            original_query="班级照片",
            normalized_query="班级照片",
            exact_terms=[],
            intent="semantic_photo_search",
            planner_contract_version="2",
            core_facets=[],
            query_constraints={
                "requires_visual_evidence": True,
                "allow_weak_only_match": False,
                "allow_vector_only_match": True,
                "min_evidence_level": "C",
                "query_core_facets": [],
            },
        )
        candidates = [
            SearchCandidate(
                photo_id=1,
                final_score=0.5,
                rrf_score=0.5,
                vector_score=0.5,
                keyword_score=0.0,
            ),
            SearchCandidate(
                photo_id=2,
                final_score=0.3,
                rrf_score=0.3,
                vector_score=0.3,
                keyword_score=0.0,
            ),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [1])
        self.assertEqual(result.filtered_out[0].photo_id, 2)
        self.assertTrue(result.trace_events[0]["allow_vector_only_match"])

    def test_entity_object_vector_only_gate_rejects_low_tag_and_caption(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            enable_semantic_tag_boost=False,
            entity_object_vector_only_min_score=0.62,
            entity_object_tag_min_score=0.62,
            entity_object_caption_min_score=0.58,
        )
        plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物",
            exact_terms=["动物"],
            intent="animal_search",
            recommended_profile="entity_object",
            core_facets=[],
            query_constraints={
                "requires_visual_evidence": True,
                "allow_weak_only_match": True,
                "min_evidence_level": "C",
                "query_core_facets": [],
            },
        )
        candidates = [
            SearchCandidate(
                photo_id=1,
                final_score=0.4,
                rrf_score=0.4,
                vector_score=0.66,
                keyword_score=0.0,
                vector_explain={"content": 0.67, "caption": 0.42, "tag": 0.41, "ocr": 0.0},
            ),
            SearchCandidate(
                photo_id=2,
                final_score=0.45,
                rrf_score=0.45,
                vector_score=0.66,
                keyword_score=0.0,
                hit_tiers={"strong"},
                vector_explain={"content": 0.60, "caption": 0.60, "tag": 0.63, "ocr": 0.0},
            ),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [2])
        self.assertEqual(result.vector_only_rejected_count, 1)
        self.assertEqual(
            result.vector_only_reject_reasons.get("vector_only_missing_tag_or_caption_evidence"),
            1,
        )

    def test_animal_intent_uses_animal_min_display_level(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_evidence_filter=True,
            min_display_evidence_level="C",
            animal_search_min_display_evidence_level="B",
            enable_semantic_tag_boost=False,
        )
        plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物",
            exact_terms=["动物"],
            intent="animal_search",
            core_facets=[],
            query_constraints={
                "requires_visual_evidence": True,
                "allow_weak_only_match": True,
                "min_evidence_level": "",
                "query_core_facets": [],
            },
        )
        candidates = [
            SearchCandidate(photo_id=1, final_score=0.5, rrf_score=0.5, hit_tiers={"strong"}),
            SearchCandidate(photo_id=2, final_score=0.45, rrf_score=0.45, vector_score=0.5),
        ]

        result = apply_post_fusion_pipeline(
            db=MagicMock(),
            candidates=candidates,
            query_plan=plan,
            settings=settings,
            project_id=1,
        )

        self.assertEqual([c.photo_id for c in result.candidates], [1])
        self.assertEqual(result.trace_events[0].get("min_display_level"), "B")


if __name__ == "__main__":
    unittest.main()
