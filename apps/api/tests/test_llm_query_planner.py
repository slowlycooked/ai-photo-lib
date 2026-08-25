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
  _build_cache_key,
    resolve_query_plan_llm_first,
)
from app.services.search.query_planner.schema import QueryPlanV2  # noqa: E402
from app.services.search.query_planner.mapper import (  # noqa: E402
    planner_v2_output_to_query_plan,
)
from app.services.query_understanding_service import understand_query  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402


def test_query_plan_v2_animals() -> None:
    plan = QueryPlanV2.model_validate(
        {
            "semantic": {"concepts": ["动物"], "queries": ["动物"]},
            "lexical": {"preferred": ["动物"]},
            "visual": {"objects": ["动物"]},
            "confidence": 0.95,
        }
    )

    assert plan.semantic.concepts == ["动物"]
    assert plan.visual.objects == ["动物"]
    assert not ({"猫", "狗", "鸟", "马"} & set(plan.semantic.concepts))


def test_query_plan_v2_location() -> None:
    plan = QueryPlanV2.model_validate(
        {"filters": {"locations": [{"name": "上海", "required": True}]}}
    )

    assert plan.filters.locations[0].name == "上海"
    assert plan.filters.locations[0].required is True


def test_query_plan_v2_location_scene() -> None:
    plan = QueryPlanV2.model_validate(
        {
            "filters": {"locations": [{"name": "上海"}]},
            "visual": {"scenes": ["夜景"]},
            "semantic": {"queries": ["城市夜景"]},
        }
    )

    assert [item.name for item in plan.filters.locations] == ["上海"]
    assert plan.visual.scenes == ["夜景"]


def test_query_plan_v2_relative_date() -> None:
    plan = QueryPlanV2.model_validate(
        {"filters": {"time_ranges": [{"start": "2025-01-01", "end": "2025-02-01"}]}}
    )

    assert plan.filters.time_ranges[0].model_dump() == {
        "start": "2025-01-01",
        "end": "2025-02-01",
    }


def test_query_plan_v2_camera() -> None:
    plan = QueryPlanV2.model_validate(
        {"filters": {"camera": [{"make": "Apple", "model_contains": "iPhone"}]}}
    )

    assert plan.filters.camera[0].make == "Apple"
    assert plan.filters.camera[0].model_contains == "iPhone"


def test_query_plan_v2_people() -> None:
    plan = QueryPlanV2.model_validate(
        {"filters": {"people": [{"name": "老王", "required": True}]}}
    )

    assert plan.filters.people[0].name == "老王"
    assert plan.filters.people[0].required is True


def test_query_plan_v2_people_compound() -> None:
    plan = QueryPlanV2.model_validate(
        {
            "filters": {
                "time_ranges": [{"start": "2025-01-01", "end": "2026-01-01"}],
                "locations": [{"name": "张家口"}],
                "people": [{"name": "老王"}],
            },
            "lexical": {"preferred": ["滑雪"]},
            "semantic": {"concepts": ["滑雪"], "queries": ["滑雪"]},
            "visual": {"scenes": ["雪地"], "activities": ["滑雪"]},
        }
    )

    assert plan.filters.people[0].name == "老王"
    assert plan.filters.locations[0].name == "张家口"
    assert plan.semantic.queries == ["滑雪"]


def test_query_plan_v2_abstract_semantic() -> None:
    plan = QueryPlanV2.model_validate(
        {"semantic": {"concepts": ["宁静"], "queries": ["宁静的氛围"]}}
    )

    assert plan.semantic.queries == ["宁静的氛围"]


def test_query_plan_v2_negative() -> None:
    plan = QueryPlanV2.model_validate(
        {"lexical": {"preferred": ["海边"], "excluded": ["下雨"]}}
    )

    assert plan.lexical.excluded == ["下雨"]


def test_query_plan_v2_adapter_maps_facts_and_semantics_without_taxonomy() -> None:
    output = QueryPlanV2.model_validate(
        {
            "filters": {
                "time_ranges": [{"start": "2025-01-01", "end": "2026-01-01"}],
                "locations": [{"name": "张家口"}],
                "people": [{"name": "老王"}],
            },
            "lexical": {"preferred": ["滑雪"]},
            "semantic": {"concepts": ["滑雪"], "queries": ["滑雪"]},
            "visual": {"scenes": ["雪地"], "activities": ["滑雪"]},
            "confidence": 0.96,
        }
    )
    deterministic = understand_query("去年张家口和老王一起滑雪", project_id=1)

    plan = planner_v2_output_to_query_plan(
        query="去年张家口和老王一起滑雪",
        output=output,
        planner_debug={"parsed": True, "confidence": 0.96},
        deterministic_plan=deterministic,
    )

    assert plan.planner_contract_version == "2"
    assert plan.metadata_filters["date_from"] == "2025-01-01"
    assert plan.metadata_filters["date_to"] == "2026-01-01"
    assert plan.metadata_filters["place_terms"] == ["张家口"]
    assert plan.planner_filters["people"] == [{"name": "老王", "required": True}]
    assert plan.semantic_query_text == "滑雪"
    assert plan.expanded_terms == ["滑雪"]
    assert plan.support_terms == ["雪地", "滑雪"]


def test_query_plan_v2_adapter_keeps_metadata_only_query_out_of_vector() -> None:
    output = QueryPlanV2.model_validate(
        {
            "filters": {
                "time_ranges": [{"start": "2025-01-01", "end": "2025-02-01"}],
                "camera": [{"make": "Apple", "model_contains": "iPhone"}],
            },
            "confidence": 0.94,
        }
    )
    deterministic = understand_query("去年1月iPhone拍的照片", project_id=1)

    plan = planner_v2_output_to_query_plan(
        query="去年1月iPhone拍的照片",
        output=output,
        planner_debug={"parsed": True, "confidence": 0.94},
        deterministic_plan=deterministic,
    )

    assert plan.metadata_filters["metadata_only"] is True
    assert plan.metadata_filters["camera_make"] == "Apple"
    assert plan.metadata_filters["camera_model"] == "iPhone"
    assert plan.semantic_query_text == ""


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
      include_raw_output=True,
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
        include_raw_output=True,
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
          include_raw_output=True,
        )

    assert plan.planner_debug.get("used_fallback") is False
    assert plan.intent == "animal_search"
    assert plan.filters.get("weather") is None
    assert plan.filters.get("time_of_day") is None
    assert plan.metadata_filters.get("year") is None
    assert plan.metadata_filters.get("month") is None
    assert plan.metadata_filters.get("season") is None
    assert plan.metadata_filters.get("camera_make") is None
    assert plan.metadata_filters.get("camera_model") is None


def test_llm_query_planner_uses_configured_timeout_without_hard_cap() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
        query_planner_timeout_seconds=30,
    )

    llm_json = """
    {
      "intent": "semantic_photo_search",
      "search_mode": "hybrid",
      "normalized_query": "复杂语义检索测试",
      "semantic_query_text": "按复杂语义检索最相关照片",
      "terms": {
        "exact": ["复杂语义检索测试"],
        "expanded": [],
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
        "time": [],
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
        "metadata_only": false,
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
      "confidence": 0.9,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ) as planner_call:
        plan = resolve_query_plan_llm_first(
            "复杂语义检索测试",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    assert plan.planner_debug.get("used_fallback") is False
    planner_call.assert_called_once()
    assert planner_call.call_args.kwargs["timeout_seconds"] == 30


def test_llm_query_planner_normalizes_metadata_month_range_string() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    llm_json = """
    {
      "intent": "location_activity_search",
      "search_mode": "semantic",
      "normalized_query": "去年在张家口的滑雪",
      "semantic_query_text": "在2025年冬季于中国张家口拍摄的滑雪活动照片",
      "terms": {
        "exact": ["滑雪", "张家口"],
        "expanded": ["滑雪场", "冬季运动"],
        "support": ["冬季"],
        "broad": ["户外活动"],
        "negative": []
      },
      "facets": {
        "object": ["雪"],
        "scene": ["雪地"],
        "activity": ["滑雪"],
        "people": ["滑雪者"],
        "weather": ["雪"],
        "time": ["冬季", "2025"],
        "location": ["张家口"]
      },
      "filters": {
        "has_people": true,
        "has_animals": false,
        "indoor_outdoor": "outdoor",
        "weather": "snowy"
      },
      "metadata_filters": {
        "year": 2025,
        "month": "1-3",
        "date_from": "2024-12-01",
        "date_to": "2025-03-31",
        "season": "winter",
        "has_gps": true,
        "place_terms": ["张家口"],
        "metadata_only": false,
        "matched_metadata_terms": ["张家口", "冬季", "滑雪"]
      },
      "concept_terms": ["滑雪", "冬季"],
      "semantic_tags": ["冬季运动", "雪景"],
      "core_facets": ["activity", "location", "weather", "time"],
      "core_facet_evidence": {
        "positive_terms": ["滑雪", "雪", "冬季", "张家口"],
        "negative_terms": []
      },
      "query_constraints": {
        "requires_visual_evidence": true,
        "allow_weak_only_match": false,
        "min_evidence_level": "high",
        "query_core_facets": ["activity", "location", "weather", "time"]
      },
      "confidence": 0.92,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ):
        plan = resolve_query_plan_llm_first(
            "去年在张家口的滑雪",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    assert plan.planner_debug.get("used_fallback") is False
    assert plan.metadata_filters.get("month") == 1


def test_llm_query_planner_uses_rule_fast_path_for_clear_short_query() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
    ) as planner_call:
        plan = resolve_query_plan_llm_first(
            "动物",
            project_id=1,
            settings=settings,
            understander=understand_query,
        )

    planner_call.assert_not_called()
    assert plan.intent == "animal_search"
    assert plan.planner_debug.get("used_fallback") is True
    assert str(plan.planner_debug.get("fallback_reason", "")).startswith("rule_fast_path:")


def test_llm_query_planner_returns_cached_plan_for_complex_query() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    query = "这组照片有一种克制但张力很强的视觉关系，请按整体语义找最接近的内容"
    llm_json = """
    {
      "intent": "semantic_photo_search",
      "search_mode": "hybrid",
      "normalized_query": "这组照片有一种克制但张力很强的视觉关系",
      "semantic_query_text": "按整体视觉关系做语义相似检索",
      "terms": {
      "exact": ["视觉关系", "整体语义"],
      "expanded": ["风格", "构图"],
      "support": [],
      "broad": [],
      "negative": []
      },
      "facets": {"object": [], "scene": [], "activity": [], "people": [], "weather": [], "time": [], "location": []},
      "filters": {},
      "metadata_filters": {"year": null, "month": null, "date_from": null, "date_to": null, "season": null, "has_gps": null, "camera_make": null, "camera_model": null, "iso_min": null, "iso_max": null, "place_terms": [], "metadata_only": false, "matched_metadata_terms": []},
      "concept_terms": [],
      "semantic_tags": ["视觉", "构图"],
      "core_facets": [],
      "core_facet_evidence": {"positive_terms": [], "negative_terms": []},
      "query_constraints": {"requires_visual_evidence": true, "allow_weak_only_match": false, "min_evidence_level": "C", "query_core_facets": []},
      "confidence": 0.92,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ) as planner_call:
        first_plan = resolve_query_plan_llm_first(
          query,
            project_id=1,
            settings=settings,
            understander=understand_query,
        )
        second_plan = resolve_query_plan_llm_first(
          query,
            project_id=1,
            settings=settings,
            understander=understand_query,
        )

    assert planner_call.call_count == 1
    assert first_plan.planner_debug.get("used_fallback") is False
    assert second_plan.planner_debug.get("cache_hit") is True


def test_llm_query_planner_cache_key_includes_runtime_context() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
        query_planner_temperature=0.3,
        query_planner_top_p=0.9,
        query_planner_max_tokens=256,
    )

    base_key = _build_cache_key(
        query="去年张家口滑雪",
        project_id=1,
        settings=settings,
        local_date="2026-06-13",
        timezone_name="Asia/Shanghai",
        system_prompt="system-a",
        user_prompt_template="template-a",
    )
    next_day_key = _build_cache_key(
        query="去年张家口滑雪",
        project_id=1,
        settings=settings,
        local_date="2026-06-14",
        timezone_name="Asia/Shanghai",
        system_prompt="system-a",
        user_prompt_template="template-a",
    )
    prompt_key = _build_cache_key(
        query="去年张家口滑雪",
        project_id=1,
        settings=settings,
        local_date="2026-06-13",
        timezone_name="Asia/Shanghai",
        system_prompt="system-b",
        user_prompt_template="template-b",
    )

    assert base_key != next_day_key
    assert base_key != prompt_key


# ---------------------------------------------------------------------------
# P0-1 regression: compound queries must NOT be fast-pathed
# ---------------------------------------------------------------------------

def test_compound_metadata_semantic_query_must_call_llm() -> None:
    """'去年张家口滑雪' has metadata (year) AND semantic residual (滑雪).
    It must NOT use the rule fast path — the LLM must be called.
    Acceptance criterion: used_fallback=false, parsed=true, latency_ms>0.
    """
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    llm_json = """
    {
      "intent": "activity_location_time_search",
      "search_mode": "hybrid",
      "normalized_query": "去年张家口滑雪",
      "semantic_query_text": "滑雪 雪地 滑雪场 冬季运动 户外运动 张家口冬季",
      "terms": {
        "exact": ["滑雪", "张家口"],
        "expanded": ["滑雪场", "雪地", "冬季运动"],
        "support": ["户外", "冬天", "旅行"],
        "broad": [],
        "negative": []
      },
      "facets": {
        "object": ["雪"],
        "scene": ["雪地", "滑雪场"],
        "activity": ["滑雪"],
        "people": [],
        "weather": ["雪"],
        "time": ["冬季", "2025"],
        "location": ["张家口"]
      },
      "filters": {"indoor_outdoor": "outdoor"},
      "metadata_filters": {
        "year": 2025,
        "date_from": "2025-01-01",
        "date_to": "2026-01-01",
        "place_terms": ["张家口"],
        "metadata_only": false,
        "matched_metadata_terms": ["去年", "张家口"]
      },
      "concept_terms": ["滑雪", "冬季运动", "雪地活动"],
      "semantic_tags": ["冬季运动", "雪景"],
      "core_facets": ["activity", "scene", "location", "time"],
      "core_facet_evidence": {
        "positive_terms": ["滑雪", "雪地", "张家口"],
        "negative_terms": []
      },
      "query_constraints": {
        "requires_visual_evidence": true,
        "allow_weak_only_match": true,
        "min_evidence_level": "C",
        "query_core_facets": ["activity", "location", "time"]
      },
      "confidence": 0.92,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ) as planner_call:
        plan = resolve_query_plan_llm_first(
            "去年张家口滑雪",
            project_id=1,
            settings=settings,
            understander=understand_query,
        )

    # LLM must have been called — not fast-pathed
    planner_call.assert_called_once()
    assert plan.planner_debug.get("used_fallback") is False
    assert plan.planner_debug.get("parsed") is True
    assert int(plan.planner_debug.get("latency_ms", -1)) >= 0
    assert plan.planner_debug.get("planner_route") == "llm"

    # Exact terms must be LLM-decomposed anchors, NOT the original sentence
    assert "去年张家口滑雪" not in plan.exact_terms
    assert "滑雪" in plan.exact_terms
    assert "张家口" in plan.exact_terms

    # Metadata filters must be correct
    assert plan.metadata_filters.get("year") == 2025
    assert plan.metadata_filters.get("metadata_only") is False
    assert "张家口" in (plan.metadata_filters.get("place_terms") or [])

    # allow_weak_only_match must be True for compound query
    assert plan.query_constraints.get("allow_weak_only_match") is True


def test_pure_metadata_query_calls_llm_when_planner_available() -> None:
    """'去年' is pure metadata, but planner-primary mode should still call LLM."""
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    llm_json = """
    {
      "intent": "metadata_filter",
      "search_mode": "hybrid",
      "normalized_query": "去年",
      "semantic_query_text": "",
      "terms": {"exact": [], "expanded": [], "support": [], "broad": [], "negative": []},
      "facets": {"object": [], "scene": [], "activity": [], "people": [], "weather": [], "time": [], "location": []},
      "filters": {"people_count_min": null, "people_count_max": null, "has_people": null, "has_animals": null, "indoor_outdoor": null, "weather": null, "time_of_day": null},
      "metadata_filters": {
        "year": 2025,
        "month": null,
        "date_from": "2025-01-01",
        "date_to": "2026-01-01",
        "season": null,
        "has_gps": null,
        "camera_make": null,
        "camera_model": null,
        "iso_min": null,
        "iso_max": null,
        "place_terms": [],
        "metadata_only": true,
        "matched_metadata_terms": ["去年"]
      },
      "concept_terms": [],
      "semantic_tags": [],
      "core_facets": [],
      "core_facet_evidence": {"positive_terms": [], "negative_terms": []},
      "query_constraints": {
        "requires_visual_evidence": false,
        "allow_weak_only_match": false,
        "min_evidence_level": "weak",
        "query_core_facets": []
      },
      "confidence": 0.9,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
    ) as planner_call:
        planner_call.return_value = llm_json
        plan = resolve_query_plan_llm_first(
            "去年",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    planner_call.assert_called_once()
    assert plan.planner_debug.get("used_fallback") is False
    assert plan.planner_debug.get("planner_route") == "llm"
    assert plan.metadata_filters.get("metadata_only") is True
    assert plan.metadata_filters.get("year") == 2025
    assert plan.exact_terms == []


def test_high_confidence_llm_plan_not_overridden_by_rule_intent() -> None:
    """Rule fallback must not rewrite high-confidence LLM intent or matched keys."""
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
      "normalized_query": "动物",
      "semantic_query_text": "抽象雕塑和图案",
      "terms": {
        "exact": ["抽象雕塑"],
        "expanded": ["图案"],
        "support": [],
        "broad": [],
        "negative": []
      },
      "facets": {
        "object": ["雕塑"],
        "scene": [],
        "activity": [],
        "people": [],
        "weather": [],
        "time": [],
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
        "metadata_only": false,
        "matched_metadata_terms": []
      },
      "concept_terms": [],
      "semantic_tags": [],
      "core_facets": ["object"],
      "core_facet_evidence": {"positive_terms": ["抽象雕塑"], "negative_terms": []},
      "query_constraints": {
        "requires_visual_evidence": true,
        "allow_weak_only_match": false,
        "min_evidence_level": "C",
        "query_core_facets": ["object"]
      },
      "confidence": 0.91,
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
            include_raw_output=True,
        )

    assert plan.planner_debug.get("planner_route") == "llm"
    assert plan.intent == "semantic_photo_search"
    assert plan.matched_keys == ["抽象雕塑", "图案"]
    assert plan.filters.get("has_animals") is not True


def test_planner_parse_failure_recovers_location_terms_from_raw_output() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3-4b-query-planner",
    )

    broken_json = """
    {
      "intent": "location-based_photo_search",
      "terms": {
        "exact": ["上海"],
        "expanded": ["上海市", "城市", "街道"]
      }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=broken_json,
    ):
        plan = resolve_query_plan_llm_first(
            "地址是上海的照片",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    assert plan.planner_debug.get("used_fallback") is True
    assert plan.intent == "metadata_location_search"
    assert "上海" in (plan.metadata_filters.get("place_terms") or [])
    assert plan.metadata_filters.get("metadata_only") is True
    assert plan.query_constraints.get("requires_visual_evidence") is False


# ---------------------------------------------------------------------------
# P0-3 regression: mapper must not pollute LLM exact terms with fallback sentence
# ---------------------------------------------------------------------------

def test_mapper_llm_exact_terms_not_polluted_by_fallback_sentence() -> None:
    """When LLM is parsed=true with confidence >= 0.6, the fallback rule engine's
    whole-sentence exact term (e.g. '去年张家口滑雪') must NOT appear in the final
    exact_terms — only the LLM-decomposed anchors should be present.
    """
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
      "normalized_query": "去年张家口滑雪",
      "semantic_query_text": "滑雪 雪地 滑雪场 冬季运动",
      "terms": {
        "exact": ["滑雪", "张家口"],
        "expanded": ["滑雪场", "雪地"],
        "support": ["冬天"],
        "broad": [],
        "negative": []
      },
      "facets": {"object": [], "scene": ["雪地"], "activity": ["滑雪"], "people": [], "weather": [], "time": [], "location": ["张家口"]},
      "filters": {},
      "metadata_filters": {
        "year": 2025,
        "place_terms": ["张家口"],
        "metadata_only": false,
        "matched_metadata_terms": ["去年", "张家口"]
      },
      "concept_terms": ["滑雪"],
      "semantic_tags": [],
      "core_facets": ["activity", "location"],
      "core_facet_evidence": {"positive_terms": ["滑雪", "张家口"], "negative_terms": []},
      "query_constraints": {"requires_visual_evidence": true, "allow_weak_only_match": true, "min_evidence_level": "C", "query_core_facets": ["activity", "location"]},
      "confidence": 0.88,
      "fallback_reason": ""
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ):
        plan = resolve_query_plan_llm_first(
            "去年张家口滑雪",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    # The whole query string must NOT appear as an exact term
    assert "去年张家口滑雪" not in plan.exact_terms, (
        f"fallback sentence polluted exact_terms: {plan.exact_terms}"
    )
    # LLM anchors must be present
    assert "滑雪" in plan.exact_terms
    assert "张家口" in plan.exact_terms
    # LLM expanded terms should not be merged with fallback
    assert "滑雪场" in plan.expanded_terms
    assert "雪地" in plan.expanded_terms


def test_llm_query_planner_maps_dynamic_filter_and_sort_controls() -> None:
    settings = replace(
        SearchSettingsResolver.defaults(),
        query_planner_enabled=True,
        query_planner_endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        query_planner_model_name="qwen3.8:27b",
    )
    llm_json = """
    {
      "intent": "group_photo_search",
      "search_mode": "hybrid",
      "normalized_query": "同学合照",
      "semantic_query_text": "同学合照",
      "terms": {"exact": ["同学", "合照"], "expanded": ["集体照"]},
      "filter_clauses": [
        {"field": "people_count", "operator": "gt", "value": 10}
      ],
      "sort": [{"field": "taken_at", "order": "desc"}],
      "confidence": 0.95
    }
    """

    with patch(
        "app.services.search.query_planner.llm_query_planner.call_chat_completion",
        return_value=llm_json,
    ):
        plan = resolve_query_plan_llm_first(
            "同学合照，人数大于10，时间倒序",
            project_id=1,
            settings=settings,
            understander=understand_query,
            include_raw_output=True,
        )

    assert plan.semantic_query_text == "同学合照"
    assert plan.filter_clauses == [
        {"field": "people_count", "operator": "gt", "value": 10}
    ]
    assert plan.sort == [{"field": "taken_at", "order": "desc"}]
