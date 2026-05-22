"""Tests for the query understanding service (rule-based query expansion & intent)."""
from __future__ import annotations

import pytest

from app.services.query_understanding_service import SearchQueryPlan, understand_query


class TestUnderstandQuery:
    def test_returns_plan_type(self):
        plan = understand_query("dog in park")
        assert isinstance(plan, SearchQueryPlan)

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

    def test_expanded_terms_are_list_of_strings(self):
        plan = understand_query("travel adventure")
        assert all(isinstance(t, str) for t in plan.expanded_terms)

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

    def test_weather_rain_strong_terms(self):
        """积水/湿地面/雨衣 should be strong (expanded), not broad."""
        plan = understand_query("下雨天")
        expanded_lower = {t.lower() for t in plan.expanded_terms}
        broad_lower = {t.lower() for t in plan.broad_terms}
        # These were previously in broad — now must be in expanded
        for strong in ("积水", "湿地面", "雨衣", "淋湿", "雨中"):
            assert strong in expanded_lower, f"{strong!r} should be in expanded_terms"
            assert strong not in broad_lower, f"{strong!r} should not be in broad_terms"

    def test_weather_rain_weak_terms(self):
        """阴天/多云/灰蒙蒙/潮湿 should be weak (broad), not strong."""
        plan = understand_query("下雨天")
        broad_lower = {t.lower() for t in plan.broad_terms}
        expanded_lower = {t.lower() for t in plan.expanded_terms}
        for weak in ("阴天", "多云", "灰蒙蒙", "潮湿"):
            assert weak in broad_lower, f"{weak!r} should be in broad_terms"
            assert weak not in expanded_lower, f"{weak!r} should not be in expanded_terms"

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
