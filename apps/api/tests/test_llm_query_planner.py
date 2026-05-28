from __future__ import annotations

import os
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.search.query_planner.llm_query_planner import (  # noqa: E402
    resolve_query_plan_llm_first,
)
from app.services.query_understanding_service import understand_query  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402


def test_llm_query_planner_disabled_uses_rule_fallback() -> None:
    settings = replace(SearchSettingsResolver.defaults(), query_planner_enabled=False)

    plan = resolve_query_plan_llm_first(
        "动物",
        project_id=1,
        settings=settings,
      understander=understand_query,
    )

    assert plan.intent == "animal_search"
    assert plan.planner_debug.get("used_fallback") is True
    assert plan.planner_debug.get("fallback_reason") == "query_planner_disabled"


def test_llm_query_planner_missing_endpoint_or_model_fallback() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="",
        query_planner_model_name="",
    )

    plan = resolve_query_plan_llm_first(
        "夜景",
        project_id=1,
        settings=settings,
      understander=understand_query,
    )

    assert plan.intent in {"location_search", "semantic_photo_search", "activity_search"}
    assert plan.planner_debug.get("used_fallback") is True
    assert plan.planner_debug.get("fallback_reason") == "query_planner_missing_endpoint_or_model"


def test_llm_query_planner_maps_output_and_merges_deterministic_metadata() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    llm_json = """
    {
      "intent": "semantic_photo_search",
      "search_mode": "hybrid",
      "normalized_query": "去年12月 iPhone 拍的照片",
      "semantic_query_text": "查找去年12月 iPhone 拍摄的照片",
      "terms": {
        "exact": ["去年12月", "iPhone"],
        "expanded": ["苹果手机"],
        "support": [],
        "broad": [],
        "negative": []
      },
      "facets": {
        "object": [],
        "scene": [],
        "activity": [],
        "people": [],
        "weather": [],
        "time": ["去年12月"],
        "location": []
      },
      "filters": {},
      "metadata_filters": {
        "year": null,
        "month": null,
        "date_from": null,
        "date_to": null,
        "season": null,
        "has_gps": null,
        "camera_make": null,
        "camera_model": null,
        "iso_min": null,
        "iso_max": null,
        "place_terms": [],
        "metadata_only": true,
        "matched_metadata_terms": []
      },
      "concept_terms": [],
      "semantic_tags": [],
      "core_facets": [],
      "core_facet_evidence": {
        "positive_terms": [],
        "negative_terms": []
      },
      "query_constraints": {
        "requires_visual_evidence": true,
        "allow_weak_only_match": false,
        "min_evidence_level": "C",
        "query_core_facets": []
      },
      "confidence": 0.88,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ):
        plan = resolve_query_plan_llm_first(
            "去年12月 iPhone 拍的照片",
            project_id=1,
            settings=settings,
        understander=understand_query,
        )

    assert plan.intent == "semantic_photo_search"
    assert plan.planner_debug.get("used_fallback") is False
    assert plan.planner_debug.get("parsed") is True
    # Deterministic parser should backfill year/month/camera fields.
    assert plan.metadata_filters.get("year") is not None
    assert plan.metadata_filters.get("month") == 12
    assert plan.metadata_filters.get("camera_make") == "Apple"


def test_llm_query_planner_accepts_empty_list_for_scalar_filters() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    llm_json = """
    {
      "intent": "search",
      "search_mode": "semantic",
      "normalized_query": "动物",
      "semantic_query_text": "关于动物的图像内容",
      "terms": {
        "exact": ["动物"],
        "expanded": ["宠物", "野生动物"],
        "support": [],
        "broad": [],
        "negative": []
      },
      "facets": {
        "object": ["动物"],
        "scene": [],
        "activity": [],
        "people": [],
        "weather": [],
        "time": [],
        "location": []
      },
      "filters": {
        "has_animals": true,
        "weather": [],
        "time_of_day": []
      },
      "metadata_filters": {
        "year": [],
        "month": [],
        "season": [],
        "camera_make": [],
        "camera_model": [],
        "place_terms": [],
        "matched_metadata_terms": []
      },
      "concept_terms": [],
      "semantic_tags": ["动物"],
      "core_facets": ["object"],
      "core_facet_evidence": {
        "positive_terms": ["动物"],
        "negative_terms": []
      },
      "query_constraints": {
        "requires_visual_evidence": true,
        "allow_weak_only_match": false,
        "min_evidence_level": "high",
        "query_core_facets": ["object"]
      },
      "confidence": 0.95,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ):
        plan = resolve_query_plan_llm_first(
            "动物",
            project_id=1,
            settings=settings,
            understander=understand_query,
        )

    assert plan.planner_debug.get("used_fallback") is False
    assert plan.filters.get("weather") is None
    assert plan.filters.get("time_of_day") is None
    assert plan.metadata_filters.get("year") is None
    assert plan.metadata_filters.get("month") is None
    assert plan.metadata_filters.get("season") is None
    assert plan.metadata_filters.get("camera_make") is None
    assert plan.metadata_filters.get("camera_model") is None
