from __future__ import annotations

import os
import unittest
from dataclasses import replace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.query_understanding_service import SearchQueryPlan  # noqa: E402
from app.services.search.people_query_resolver import (  # noqa: E402
    PeopleQueryResolution,
    ResolvedPersonRef,
)
from app.services.search.search_plan_builder import build_search_plan  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402


class SearchPlanBuilderTest(unittest.TestCase):
    def test_metadata_only_is_blocked_for_strong_semantic_intent(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_structured_filters=True,
        )
        query_plan = SearchQueryPlan(
            original_query="动物",
            normalized_query="动物",
            exact_terms=["动物"],
            intent="animal_search",
            metadata_filters={"metadata_only": True, "year": 2024},
        )
        people_resolution = PeopleQueryResolution(
            query="动物",
            residual_query="动物",
            people_filter_mode="none",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="动物",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        self.assertFalse(plan.metadata_only_allowed)
        self.assertEqual(plan.metadata_filter_skipped_reason, "strong_semantic_intent")
        self.assertFalse(plan.metadata_filters.get("metadata_only"))

    def test_people_query_preserves_temporal_metadata_constraint(self) -> None:
        settings = SearchSettingsResolver.defaults()
        query_plan = SearchQueryPlan(
            original_query="小明",
            normalized_query="小明",
            exact_terms=["小明"],
            intent="people_search",
            metadata_filters={"year": 2020, "metadata_only": True},
        )
        people_resolution = PeopleQueryResolution(
            query="小明",
            residual_query="",
            people_filter_mode="any",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="小明",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        self.assertEqual(plan.metadata_filters.get("year"), 2020)
        self.assertFalse(plan.metadata_filters.get("metadata_only"))
        self.assertEqual(plan.effective_mode, settings.default_mode)

    def test_v2_people_compound_preserves_metadata_and_plans_once(self) -> None:
        settings = SearchSettingsResolver.defaults()
        query_plan = SearchQueryPlan(
            original_query="去年和老王一起滑雪",
            normalized_query="去年和老王一起滑雪",
            semantic_query_text="滑雪",
            expanded_terms=["滑雪"],
            intent="semantic_photo_search",
            metadata_filters={
                "date_from": "2025-01-01",
                "date_to": "2026-01-01",
                "metadata_only": False,
            },
            planner_contract_version="2",
            planner_filters={
                "people": [{"name": "老王", "required": True}],
                "time_ranges": [
                    {"start": "2025-01-01", "end": "2026-01-01"}
                ],
            },
            lexical_plan={"required": [], "preferred": ["滑雪"], "excluded": []},
            semantic_plan={"concepts": ["滑雪"], "queries": ["滑雪"]},
            visual_plan={"objects": [], "scenes": [], "activities": ["滑雪"], "attributes": []},
        )
        people_resolution = PeopleQueryResolution(
            query="去年和老王一起滑雪",
            residual_query="滑雪",
            people_filter_mode="any",
            matched_people=[
                ResolvedPersonRef(
                    person_id=7,
                    display_name="老王",
                    normalized_name="老王",
                    matched_term="老王",
                )
            ],
        )
        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings
        query_plan_resolver = MagicMock(return_value=query_plan)

        plan = build_search_plan(
            db=MagicMock(),
            query="去年和老王一起滑雪",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=query_plan_resolver,
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        query_plan_resolver.assert_called_once()
        self.assertIs(plan.search_query_plan, query_plan)
        self.assertEqual(plan.metadata_filters["date_from"], "2025-01-01")
        self.assertEqual(plan.metadata_filters["date_to"], "2026-01-01")
        self.assertEqual(plan.people_query_plan["semantic_query"], "滑雪")

    def test_auto_mode_uses_keyword_for_ocr_intent(self) -> None:
        settings = replace(SearchSettingsResolver.defaults(), default_mode="hybrid")
        ocr_plan = SearchQueryPlan(
            original_query="路牌文字",
            normalized_query="路牌文字",
            exact_terms=["路牌文字"],
            intent="ocr_text_search",
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="路牌文字",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=ocr_plan),
            people_query_resolver=MagicMock(
                return_value=PeopleQueryResolution(
                    query="路牌文字",
                    residual_query="路牌文字",
                    people_filter_mode="none",
                    matched_people=[],
                )
            ),
        )

        self.assertEqual(plan.effective_mode, "keyword")

    def test_metadata_only_is_allowed_for_semantic_metadata_query(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_structured_filters=True,
        )
        query_plan = SearchQueryPlan(
            original_query="去年的照片",
            normalized_query="去年",
            exact_terms=["去年"],
            intent="semantic_photo_search",
            metadata_filters={"metadata_only": True, "year": 2025},
        )
        people_resolution = PeopleQueryResolution(
            query="去年的照片",
            residual_query="去年的照片",
            people_filter_mode="none",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="去年的照片",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        self.assertTrue(plan.metadata_only_allowed)
        self.assertEqual(plan.metadata_filter_skipped_reason, "not_skipped")
        self.assertTrue(plan.metadata_filters.get("metadata_only"))

    def test_temporal_metadata_filters_are_forced_when_structured_filters_disabled(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_structured_filters=False,
        )
        query_plan = SearchQueryPlan(
            original_query="去年的照片",
            normalized_query="去年",
            exact_terms=["去年"],
            intent="semantic_photo_search",
            metadata_filters={
                "metadata_only": True,
                "year": 2025,
                "date_from": "2025-01-01",
                "date_to": "2026-01-01",
            },
        )
        people_resolution = PeopleQueryResolution(
            query="去年的照片",
            residual_query="去年的照片",
            people_filter_mode="none",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="去年的照片",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        self.assertTrue(plan.metadata_filter_active)
        self.assertEqual(plan.metadata_filter_skipped_reason, "forced_temporal_metadata")
        self.assertEqual(plan.metadata_filters.get("year"), 2025)
        self.assertTrue(plan.metadata_filters.get("metadata_only"))

    def test_location_metadata_filters_are_forced_when_structured_filters_disabled(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_structured_filters=False,
        )
        query_plan = SearchQueryPlan(
            original_query="地址是上海的照片",
            normalized_query="上海",
            exact_terms=["上海"],
            intent="metadata_location_search",
            metadata_filters={
                "metadata_only": True,
                "place_terms": ["上海", "上海市"],
                "matched_metadata_terms": ["上海"],
            },
        )
        people_resolution = PeopleQueryResolution(
            query="地址是上海的照片",
            residual_query="地址是上海的照片",
            people_filter_mode="none",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="地址是上海的照片",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
        )

        self.assertTrue(plan.metadata_filter_active)
        self.assertEqual(plan.metadata_filter_skipped_reason, "forced_location_metadata")
        self.assertEqual(plan.metadata_filters.get("place_terms"), ["上海", "上海市"])
        self.assertTrue(plan.metadata_filters.get("metadata_only"))

    def test_dynamic_location_metadata_applies_on_planner_fallback(self) -> None:
        settings = replace(
            SearchSettingsResolver.defaults(),
            enable_structured_filters=False,
        )
        query_plan = SearchQueryPlan(
            original_query="深圳",
            normalized_query="深圳",
            exact_terms=["深圳"],
            intent="semantic_photo_search",
            metadata_filters={},
            planner_debug={
                "used_fallback": True,
                "fallback_reason": "planner_timeout_fallback",
            },
        )
        people_resolution = PeopleQueryResolution(
            query="深圳",
            residual_query="深圳",
            people_filter_mode="none",
            matched_people=[],
        )

        resolver = MagicMock()
        resolver.resolve.return_value = settings
        resolver.defaults.return_value = settings

        plan = build_search_plan(
            db=MagicMock(),
            query="深圳",
            mode="auto",
            project_id=1,
            face_filter_active=False,
            settings_resolver_cls=resolver,
            query_plan_resolver=MagicMock(return_value=query_plan),
            people_query_resolver=MagicMock(return_value=people_resolution),
            dynamic_location_resolver=MagicMock(return_value=["深圳"]),
        )

        self.assertEqual(plan.search_query_plan.intent, "metadata_location_search")
        self.assertTrue(plan.metadata_filter_active)
        self.assertEqual(plan.metadata_filter_skipped_reason, "forced_location_metadata")
        self.assertEqual(plan.metadata_filters.get("place_terms"), ["深圳"])
        self.assertTrue(plan.metadata_filters.get("metadata_only"))


if __name__ == "__main__":
    unittest.main()
