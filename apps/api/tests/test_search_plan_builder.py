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
from app.services.search.people_query_resolver import PeopleQueryResolution  # noqa: E402
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

    def test_people_only_query_clears_metadata_filters(self) -> None:
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

        self.assertEqual(plan.metadata_filters, {})
        self.assertEqual(plan.effective_mode, settings.default_mode)

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


if __name__ == "__main__":
    unittest.main()
