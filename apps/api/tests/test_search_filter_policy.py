from __future__ import annotations

import os
import unittest
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.query_understanding_service import understand_query  # noqa: E402
from app.services.search.filter_policy import core_facet_passes  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.search.types import SearchCandidate  # noqa: E402


class SearchFilterPolicyTest(unittest.TestCase):
    def test_night_core_facet_uses_architecture_pack_positive_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("夜景", rule_base_pack_id="architecture_default")
        candidate = SearchCandidate(photo_id=1, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["建筑照明"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertTrue(passes)
        self.assertEqual(reason, "night_positive_evidence")

    def test_night_core_facet_uses_architecture_pack_negative_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("夜景", rule_base_pack_id="architecture_default")
        candidate = SearchCandidate(photo_id=2, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["建筑照明", "办公日景"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertFalse(passes)
        self.assertEqual(reason, "night_conflicting_evidence")

    def test_indoor_core_facet_uses_pack_positive_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("室内")
        candidate = SearchCandidate(photo_id=3, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["室内场景"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertTrue(passes)
        self.assertEqual(reason, "indoor_positive_visual_evidence")

    def test_indoor_core_facet_uses_pack_negative_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("室内")
        candidate = SearchCandidate(photo_id=4, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["室内场景", "户外"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertFalse(passes)
        self.assertEqual(reason, "indoor_conflicting_evidence")

    def test_indoor_core_facet_uses_pack_query_trigger_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("室内空间", rule_base_pack_id="architecture_default")
        candidate = SearchCandidate(photo_id=7, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["室内采光"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertTrue(passes)
        self.assertEqual(reason, "indoor_positive_visual_evidence")

    def test_animal_core_facet_uses_pack_generic_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("动物")
        candidate = SearchCandidate(photo_id=5, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=[],
            object_tags=["宠物"],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
            semantic_concepts=[],
            raw_result={},
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertFalse(passes)
        self.assertEqual(reason, "animal_no_entity_evidence")

    def test_animal_core_facet_uses_pack_weak_scene_terms(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            require_core_facet_match=True,
            allow_vector_only_for_facet_query=False,
        )
        query_plan = understand_query("动物")
        candidate = SearchCandidate(photo_id=6, vector_score=0.1, evidence_level="C")
        ai_analysis = SimpleNamespace(
            caption="",
            ocr_text="",
            scene_tags=["动物园"],
            object_tags=[],
            activity_tags=[],
            search_keywords=[],
            location_clues=[],
            semantic_concepts=[],
            raw_result={},
        )

        passes, reason = core_facet_passes(candidate, ai_analysis, query_plan, settings)

        self.assertFalse(passes)
        self.assertEqual(reason, "animal_scene_without_entity")


if __name__ == "__main__":
    unittest.main()