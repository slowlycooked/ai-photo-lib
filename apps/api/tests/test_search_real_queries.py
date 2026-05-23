from __future__ import annotations

import pytest

from app.services.query_understanding_service import understand_query


@pytest.mark.parametrize(
    "query,expected_intent,expected_mode",
    [
        ("室内", "semantic_photo_search", "hybrid"),
        ("夜景", "location_search", "hybrid"),
        ("海边", "location_search", "hybrid"),
        ("下雨天", "weather_search", "hybrid"),
        ("猫", "animal_search", "hybrid"),
        ("订单号", "ocr_text_search", "keyword"),
        ("发票", "ocr_text_search", "keyword"),
        ("有GPS", "semantic_photo_search", "hybrid"),
        ("2024年12月", "ocr_text_search", "keyword"),
        ("iPhone拍的", "semantic_photo_search", "hybrid"),
    ],
)
def test_real_query_regression_intent_and_mode(
    query: str,
    expected_intent: str,
    expected_mode: str,
) -> None:
    plan = understand_query(query)
    assert plan.intent == expected_intent
    assert plan.search_mode == expected_mode


def test_real_query_regression_metadata_queries_keep_structured_filters() -> None:
    plan = understand_query("2024年12月 iPhone 有GPS")
    assert plan.metadata_filters["year"] == 2024
    assert plan.metadata_filters["month"] == 12
    assert plan.metadata_filters["camera_make"] == "Apple"
    assert plan.metadata_filters["has_gps"] is True


def test_real_query_regression_semantic_light_mode() -> None:
    plan = understand_query("室内")
    assert plan.intent == "semantic_photo_search"
    assert len(plan.expanded_terms) <= 3
    assert plan.support_terms == []
    assert plan.broad_terms == []
