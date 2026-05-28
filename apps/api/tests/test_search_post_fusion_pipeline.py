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


if __name__ == "__main__":
    unittest.main()
