"""Tests for the query understanding service (rule-based query expansion & intent)."""
from __future__ import annotations

import pytest

from app.services.query_understanding_service import SearchQueryPlan, understand_query
from app.services.search.debug import build_debug_payload
from app.services.search.query_understanding import build_query_plan_trace_event
from app.services.search.settings_resolver import SearchSettingsResolver


class TestUnderstandQuery:
    def test_returns_plan_type(self):
        plan = understand_query("dog in park")
        assert isinstance(plan, SearchQueryPlan)

    def test_extracts_dynamic_controls_from_semantic_query(self):
        plan = understand_query("同学合照，人数大于10，时间倒序")

        assert "同学合照" in plan.semantic_query_text
        assert "人数大于10" not in plan.semantic_query_text
        assert "时间倒序" not in plan.semantic_query_text
        assert plan.filter_clauses == [
            {"field": "people_count", "operator": "gt", "value": 10}
        ]
        assert plan.sort == [{"field": "taken_at", "order": "desc"}]

    def test_control_only_query_does_not_restore_controls_as_semantic_text(self):
        plan = understand_query("人数大于10，时间倒序")

        assert plan.semantic_query_text == ""
        assert plan.exact_terms == []
        assert plan.filter_clauses == [
            {"field": "people_count", "operator": "gt", "value": 10}
        ]
        assert plan.sort == [{"field": "taken_at", "order": "desc"}]

    def test_extracts_prefix_people_count_without_polluting_semantics(self):
        plan = understand_query("至少10人的班级照片")

        assert "班级" in plan.semantic_query_text
        assert "至少10人" not in plan.semantic_query_text
        assert plan.filter_clauses == [
            {"field": "people_count", "operator": "gte", "value": 10}
        ]

    def test_keeps_open_ended_semantics_without_inventing_controls(self):
        plan = understand_query("海边划船多人")

        assert "海边" in plan.semantic_query_text
        assert "划船" in plan.semantic_query_text
        assert plan.filter_clauses == []
        assert plan.sort == []

    def test_original_query_preserved(self):
        plan = understand_query("sunset photo")
        assert plan.original_query == "sunset photo"

    def test_animal_query_expands_terms(self):
        plan = understand_query("dog")
        # expanded_terms = close synonyms (狗/小狗)
        assert len(plan.expanded_terms) >= 1
        # broad_terms = category terms (宠物, 动物)
        assert any("宠物" in t or "动物" in t for t in plan.broad_terms)
        # all_terms combines all three tiers
        all_t = plan.all_terms
        assert any("狗" in t or "宠物" in t or "动物" in t for t in all_t)

    def test_category_animal_query_builds_semantic_query_text(self):
        plan = understand_query("动物")

        assert plan.intent == "animal_search"
        assert "查找包含动物主体的照片" in plan.semantic_query_text
        assert "猫" in plan.semantic_query_text
        assert "狗" in plan.semantic_query_text

    def test_small_animal_query_expands_rabbit(self):
        plan = understand_query("小动物")
        expanded_lower = {t.lower() for t in plan.expanded_terms}

        assert plan.intent == "animal_search"
        assert "兔子" in expanded_lower
        assert "猫" in expanded_lower

    def test_animal_intent_detected(self):
        plan = understand_query("cat playing")
        assert plan.intent == "animal_search"

    def test_weather_query_expands(self):
        plan = understand_query("rainy day")
        # rain / 雨 terms appear in expanded or broad
        assert any("雨" in t for t in plan.all_terms)

    def test_weather_intent_detected(self):
        plan = understand_query("雪天照片")
        assert plan.intent == "weather_search"

    def test_ocr_query_uses_keyword_mode(self):
        """Queries that look like OCR text / identifiers should use keyword mode."""
        plan = understand_query("invoice 20240101")
        assert plan.search_mode == "keyword"

    def test_generic_query_uses_hybrid_mode(self):
        plan = understand_query("hiking in mountains")
        assert plan.search_mode == "hybrid"

    def test_normalized_query_is_string(self):
        plan = understand_query("sunset beach vacation")
        assert isinstance(plan.normalized_query, str)
        assert len(plan.normalized_query) > 0

    def test_empty_after_strip_handled(self):
        """Whitespace-only query should still return a plan without crashing."""
        plan = understand_query("  ")
        assert plan.original_query == ""

    def test_project_id_accepted(self):
        """project_id parameter should be accepted without error."""
        plan = understand_query("building facade", project_id=42)
        assert plan.original_query == "building facade"

    def test_two_projects_get_independent_plans(self):
        """Query understanding must be stateless — results must not bleed between projects."""
        plan_a = understand_query("sunset", project_id=1)
        plan_b = understand_query("sunset", project_id=2)
        # Both plans should be independent instances
        assert plan_a is not plan_b
        assert plan_a.original_query == plan_b.original_query

    def test_food_query_expands(self):
        plan = understand_query("美食拍摄")
        assert any("食物" in t or "料理" in t or "美食" in t for t in plan.all_terms)

    def test_family_animal_scene_query_expands_people_and_scene_terms(self):
        plan = understand_query("爸爸和动物的合影")
        expanded_lower = {t.lower() for t in plan.expanded_terms}

        assert plan.intent == "animal_search"
        assert "爸爸" in plan.matched_keys
        assert "动物" in plan.matched_keys
        assert "合影" in plan.matched_keys
        assert any(term in expanded_lower for term in ("父亲", "家庭", "亲子"))
        assert any(term in expanded_lower for term in ("动物", "野生动物"))

    def test_daughter_zoo_query_expands_family_and_zoo_terms(self):
        plan = understand_query("女儿在动物园")
        expanded_lower = {t.lower() for t in plan.expanded_terms}

        assert plan.intent == "animal_search"
        assert "女儿" in plan.matched_keys
        assert "动物园" in plan.matched_keys
        assert any(term in expanded_lower for term in ("孩子", "儿童", "亲子", "家庭"))
        assert any(term in expanded_lower for term in ("动物", "野生动物"))

    def test_expanded_terms_are_list_of_strings(self):
        plan = understand_query("travel adventure")
        assert all(isinstance(t, str) for t in plan.expanded_terms)

    def test_query_understanding_group_photo(self):
        plan = understand_query("合照")
        expanded = set(plan.expanded_terms)

        assert plan.intent in {"people_search", "group_photo_search"}
        assert "合影" in expanded
        assert "集体照" in expanded
        assert "多人" in expanded
        assert "people" in plan.core_facets
        assert "group_photo" in plan.core_facets
        assert plan.recommended_profile == "people_group"

    @pytest.mark.parametrize("query", ["合影", "集体照", "多人合照"])
    def test_query_understanding_group_photo_aliases(self, query: str):
        plan = understand_query(query)

        assert plan.intent in {"people_search", "group_photo_search"}
        assert "people" in plan.core_facets
        assert "group_photo" in plan.core_facets

    # ── P1: recall_terms excludes weak/broad terms ────────────────────────────

    def test_recall_terms_excludes_broad(self):
        """broad_terms must NOT appear in recall_terms."""
        plan = understand_query("下雨天")
        recall = set(plan.recall_terms)
        for broad in plan.broad_terms:
            assert broad not in recall, f"broad term {broad!r} leaked into recall_terms"

    def test_recall_terms_contains_exact_and_expanded(self):
        """recall_terms should contain exact and expanded (strong) terms only."""
        plan = understand_query("下雨天")
        recall = set(plan.recall_terms)
        # exact terms must be in recall
        for t in plan.exact_terms:
            assert t in recall
        # expanded (strong) terms must be in recall
        for t in plan.expanded_terms:
            assert t in recall

    def test_weather_rain_support_terms(self):
        """积水/湿地面/雨衣 should be support terms, not broad terms."""
        plan = understand_query("下雨天")
        support_lower = {t.lower() for t in plan.support_terms}
        broad_lower = {t.lower() for t in plan.broad_terms}
        # Support terms should provide context but not be weak broad terms.
        for support in ("积水", "湿地面", "雨衣", "淋湿"):
            assert support in support_lower, f"{support!r} should be in support_terms"
            assert support not in broad_lower, f"{support!r} should not be in broad_terms"

        # Keep rain-core evidence term in expanded tier.
        assert "雨中" in {t.lower() for t in plan.expanded_terms}

    def test_weather_rain_weak_terms(self):
        """阴天/多云/灰蒙蒙/潮湿 should be weak (broad), not strong."""
        plan = understand_query("下雨天")
        broad_lower = {t.lower() for t in plan.broad_terms}
        expanded_lower = {t.lower() for t in plan.expanded_terms}
        for weak in ("阴天", "多云", "灰蒙蒙", "潮湿"):
            assert weak in broad_lower, f"{weak!r} should be in broad_terms"
            assert weak not in expanded_lower, f"{weak!r} should not be in expanded_terms"

    def test_indoor_query_uses_lightweight_semantic_expansion(self):
        """纯“室内”查询在 semantic 模式下仅保留少量 expanded，不再扩 support/broad。"""
        plan = understand_query("室内")
        expanded_lower = {t.lower() for t in plan.expanded_terms}
        support_lower = {t.lower() for t in plan.support_terms}
        broad_lower = {t.lower() for t in plan.broad_terms}

        assert "家庭" not in expanded_lower
        assert "家" not in expanded_lower
        assert support_lower == set()
        assert broad_lower == set()
        assert 1 <= len(plan.expanded_terms) <= 3
        assert any(t in expanded_lower for t in ("客厅", "卧室", "厨房", "家具", "房间"))

    def test_rain_penalize_tags_populated(self):
        """下雨天 should produce non-empty penalize_tags."""
        plan = understand_query("下雨天")
        assert len(plan.penalize_tags) > 0
        # 室内 should definitely be penalized for rain search
        assert "室内" in plan.penalize_tags

    def test_no_penalize_tags_for_generic_query(self):
        """A generic non-weather query should have empty penalize_tags."""
        plan = understand_query("beautiful landscape")
        assert plan.penalize_tags == []

    def test_recall_terms_is_subset_of_all_terms(self):
        """recall_terms ⊆ all_terms always."""
        for query in ("下雨天", "爬山", "cat", "日落海边", "美食"):
            plan = understand_query(query)
            all_set = set(plan.all_terms)
            for t in plan.recall_terms:
                assert t in all_set, f"{t!r} in recall_terms but not in all_terms for query {query!r}"


@pytest.mark.parametrize(
    "query,expected_intent,expected_mode",
    [
        ("下雨天", "weather_search", "hybrid"),
        ("夜景", "location_search", "hybrid"),
        ("invoice 20240101", "ocr_text_search", "keyword"),
    ],
)
def test_query_understanding_behavior_contract_intent_and_mode(
    query: str,
    expected_intent: str,
    expected_mode: str,
):
    plan = understand_query(query)
    assert plan.intent == expected_intent
    assert plan.search_mode == expected_mode


def test_query_understanding_behavior_contract_metadata_only_query():
    plan = understand_query("2024年12月 iPhone 有GPS 的照片")
    metadata = plan.metadata_filters
    assert metadata["metadata_only"] is True
    assert metadata["year"] == 2024
    assert metadata["month"] == 12
    assert metadata["camera_make"] == "Apple"
    assert metadata["has_gps"] is True


def test_query_understanding_parses_camera_next_to_chinese_text():
    metadata = understand_query("去年1月iPhone拍的照片").metadata_filters

    assert metadata["camera_make"] == "Apple"
    assert metadata["camera_model"] == "iPhone"
    assert metadata["place_terms"] == []


def test_query_understanding_behavior_contract_time_and_place_query():
    plan = understand_query("2024年5月 杭州的照片")
    metadata = plan.metadata_filters
    assert metadata["metadata_only"] is True
    assert metadata["year"] == 2024
    assert metadata["month"] == 5
    assert metadata["place_terms"] == ["杭州"]


def test_query_plan_v2_trace_and_debug_expose_resolved_retriever_inputs():
    plan = SearchQueryPlan(
        original_query="去年老王在上海滑雪",
        normalized_query="去年老王在上海滑雪",
        semantic_query_text="滑雪",
        exact_terms=["滑雪"],
        expanded_terms=["雪地"],
        intent="semantic_photo_search",
        metadata_filters={
            "date_from": "2025-01-01",
            "date_to": "2026-01-01",
            "place_terms": ["上海"],
        },
        planner_debug={
            "planner_route": "llm",
            "fallback_reason": "",
            "latency_ms": 17,
        },
        planner_contract_version="2",
        planner_filters={
            "time_ranges": [{"start": "2025-01-01", "end": "2026-01-01"}],
            "locations": [{"name": "上海", "required": True}],
            "people": [{"name": "老王", "required": True}],
        },
        lexical_plan={"required": ["滑雪"], "preferred": ["雪地"], "excluded": []},
        semantic_plan={"concepts": ["滑雪"], "queries": ["滑雪"]},
        visual_plan={"objects": [], "scenes": ["雪地"], "activities": ["滑雪"], "attributes": []},
        unresolved_entities={"people": [], "locations": []},
    )
    trace = [
        build_query_plan_trace_event(plan),
        {
            "stage": "keyword_recall",
            "keyword_query_text": "滑雪 雪地",
            "keyword_query_terms": ["滑雪", "雪地"],
            "duration_ms": 3,
        },
        {
            "stage": "vector_recall",
            "vector_query_text": "滑雪",
            "vector_query_source": "qwen",
            "duration_ms": 5,
        },
        {"stage": "result", "duration_ms": 2, "total_ms": 31},
    ]

    payload = build_debug_payload(
        query_plan=plan,
        mode="hybrid",
        embedding_model="test",
        embedding_dimension=1024,
        keyword_candidates=4,
        vector_candidates=3,
        merged_candidates=5,
        fallback_reason="",
        settings=SearchSettingsResolver.defaults(),
        trace=trace,
        metadata_filters=plan.metadata_filters,
        matched_person_ids=[101],
    )

    assert trace[0]["planner_contract_version"] == "2"
    assert trace[0]["filters"]["locations"][0]["name"] == "上海"
    assert payload["query_plan"]["semantic"]["queries"] == ["滑雪"]
    assert payload["retrieval_queries"] == {
        "keyword_query_text": "滑雪 雪地",
        "keyword_query_terms": ["滑雪", "雪地"],
        "vector_query_text": "滑雪",
        "vector_query_source": "qwen",
    }
    assert payload["resolved_constraints"]["matched_person_ids"] == [101]
    assert payload["timings_ms"]["planner_ms"] == 17
    assert payload["timings_ms"]["keyword_ms"] == 3
    assert payload["timings_ms"]["vector_ms"] == 5
    assert payload["timings_ms"]["total_ms"] == 31


def test_query_understanding_location_metadata_query_uses_metadata_location_intent() -> None:
    plan = understand_query("地址是上海的照片")

    assert plan.intent == "metadata_location_search"
    assert plan.semantic_query_text == ""
    assert plan.exact_terms == ["上海"]
    assert plan.metadata_filters["metadata_only"] is True
    assert plan.metadata_filters["place_terms"] == ["上海"]
    assert plan.query_constraints["requires_visual_evidence"] is False
    assert plan.query_constraints["requires_metadata_evidence"] is True


def test_query_understanding_composite_place_query_keeps_semantic_residual() -> None:
    plan = understand_query("上海的猫")

    assert plan.metadata_filters["place_terms"] == ["上海"]
    assert plan.metadata_filters["metadata_only"] is False
    assert plan.intent in {"animal_search", "semantic_photo_search"}


def test_query_understanding_time_only_semantic_query_relaxes_visual_constraints():
    plan = understand_query("去年的照片")

    metadata = plan.metadata_filters
    constraints = plan.query_constraints

    assert plan.intent == "semantic_photo_search"
    assert metadata["metadata_only"] is True
    assert metadata["year"] is not None
    assert constraints["requires_visual_evidence"] is False
    assert constraints["allow_weak_only_match"] is True


def test_query_understanding_last_year_activity_is_not_misread_as_place_only():
    plan = understand_query("去年滑雪")

    metadata = plan.metadata_filters
    constraints = plan.query_constraints

    assert metadata["year"] is not None
    assert metadata["place_terms"] == []
    assert metadata["metadata_only"] is False
    assert constraints["requires_visual_evidence"] is True
    assert constraints["allow_weak_only_match"] is False


def test_query_understanding_zhangjiakou_skiing_avoids_indoor_false_positive() -> None:
    plan = understand_query("去年在张家口的滑雪")

    metadata = plan.metadata_filters
    assert "家" not in plan.matched_keys
    assert "卧室" not in plan.expanded_terms
    assert "客厅" not in plan.expanded_terms
    assert "室内" not in plan.expanded_terms
    assert metadata["year"] is not None
    assert metadata["place_terms"] == ["张家口"]
    assert metadata["metadata_only"] is False


def test_query_understanding_behavior_contract_folder_filter_agnostic():
    """Folder filtering is handled in search SQL layer, not query understanding."""
    plan = understand_query("夜景")
    assert plan.filters.get("location") is None
    assert plan.search_mode == "hybrid"


def test_query_understanding_architecture_base_pack_changes_rule_domain():
    default_plan = understand_query("立面")
    architecture_plan = understand_query(
        "立面",
        rule_base_pack_id="architecture_default",
    )

    assert default_plan.intent == "semantic_photo_search"
    assert architecture_plan.intent in {"activity_search", "location_search"}
    assert "立面" in architecture_plan.matched_keys


def test_query_understanding_extension_pack_expands_terms():
    plan = understand_query(
        "trail",
        rule_extension_pack_ids=["travel_outdoor_extension"],
    )

    expanded = {term.lower() for term in plan.expanded_terms}
    assert plan.intent == "activity_search"
    assert "trail" in plan.matched_keys
    assert "步道" in expanded


def test_query_understanding_unknown_rule_pack_fails_explicitly():
    with pytest.raises(ValueError, match="Unknown query understanding pack"):
        understand_query("dog", rule_base_pack_id="missing_pack")


def test_query_understanding_night_query_emits_pack_driven_core_facet_evidence():
    plan = understand_query("夜景")

    assert "night" in plan.core_facet_evidence
    assert "灯光" in plan.core_facet_evidence["night"]["positive_terms"]
    assert "白天" in plan.core_facet_evidence["night"]["negative_terms"]


def test_query_understanding_indoor_query_emits_domain_evidence():
    plan = understand_query("室内")

    assert "indoor" in plan.core_facet_evidence
    assert "室内" in plan.core_facet_evidence["indoor"]["positive_terms"]
    assert "户外" in plan.core_facet_evidence["indoor"]["negative_terms"]
    assert "室内" in plan.core_facet_evidence["indoor"]["query_triggers"]


def test_query_understanding_animal_query_emits_generic_and_entity_hints():
    plan = understand_query("动物")

    assert "animal" in plan.core_facet_evidence
    assert "动物" in plan.core_facet_evidence["animal"]["generic_terms"]
    assert "猫" in plan.core_facet_evidence["animal"]["entity_hints"]
    assert "动物园" in plan.core_facet_evidence["animal"]["weak_scene_terms"]
