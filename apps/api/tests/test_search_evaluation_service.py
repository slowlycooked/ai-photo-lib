from __future__ import annotations

import unittest

from app.services.search.search_evaluation_catalog import (
    SEARCH_EVALUATION_BASELINES,
    SEARCH_PLANNER_DEBUG_EVALUATION_SET,
)
from app.services.search.search_evaluation_service import (
    SearchEvaluationCase,
    SearchEvaluationService,
)


class SearchEvaluationServiceTest(unittest.TestCase):
    def test_evaluate_cases_passes_when_expected_ids_are_returned(self) -> None:
        calls: list[dict] = []

        def _search_fn(db, query, **kwargs):
            calls.append({"db": db, "query": query, **kwargs})
            return 2, [{"photo_id": 11}, {"photo_id": 12}], None

        service = SearchEvaluationService(object(), 7, search_fn=_search_fn)
        results = service.evaluate_cases(
            [
                SearchEvaluationCase(
                    name="animal baseline",
                    query="动物",
                    expected_photo_ids=(11,),
                    min_total=1,
                )
            ]
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].returned_photo_ids, (11, 12))
        self.assertEqual(calls[0]["project_id"], 7)
        self.assertEqual(calls[0]["page_size"], 20)
        self.assertFalse(calls[0]["debug"])

    def test_evaluate_cases_fails_when_expected_ids_are_missing(self) -> None:
        def _search_fn(_db, _query, **_kwargs):
            return 1, [{"photo_id": 22}], None

        service = SearchEvaluationService(object(), 9, search_fn=_search_fn)
        results = service.evaluate_cases(
            [
                SearchEvaluationCase(
                    name="night baseline",
                    query="夜景",
                    expected_photo_ids=(99,),
                    min_total=1,
                )
            ],
            page_size=5,
        )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)
        self.assertEqual(results[0].returned_photo_ids, (22,))
        self.assertIn("missing expected ids", results[0].reason)

    def test_evaluate_cases_fails_when_total_is_below_minimum(self) -> None:
        def _search_fn(_db, _query, **_kwargs):
            return 0, [], None

        service = SearchEvaluationService(object(), 9, search_fn=_search_fn)
        results = service.evaluate_cases(
            [
                SearchEvaluationCase(
                    name="ocr baseline",
                    query="门牌号",
                    min_total=1,
                )
            ]
        )

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].passed)
        self.assertEqual(results[0].reason, "total 0 < min_total 1")

    def test_evaluate_cases_checks_expected_plan_when_debug_enabled(self) -> None:
        def _search_fn(_db, _query, **_kwargs):
            return 1, [{"photo_id": 12}], {
                "query_planner": {"planner_route": "llm"},
                "semantic_query_text": "滑雪 雪地",
                "metadata_filters": {
                    "year": 2025,
                    "place_terms": ["张家口"],
                },
                "term_groups": {
                    "must": ["滑雪"],
                    "negative": [],
                },
                "intent": "activity_search",
            }

        service = SearchEvaluationService(object(), 9, search_fn=_search_fn)
        results = service.evaluate_cases(
            [
                SearchEvaluationCase(
                    name="planner assertion",
                    query="去年张家口滑雪",
                    expected_plan={
                        "planner_route": "llm",
                        "intent": "activity_search",
                        "semantic_query": "non_empty",
                        "metadata": {
                            "year_present": True,
                            "place_terms_contains": ["张家口"],
                        },
                        "term_groups_contains": {"must": ["滑雪"]},
                    },
                )
            ],
            debug=True,
        )

        self.assertTrue(results[0].passed)
        self.assertEqual(results[0].reason, "ok")

    def test_evaluate_cases_fails_expected_plan_mismatch(self) -> None:
        def _search_fn(_db, _query, **_kwargs):
            return 1, [{"photo_id": 12}], {
                "query_planner": {"planner_route": "rule_fast_path"},
                "semantic_query_text": "",
                "metadata_filters": {},
                "term_groups": {"must": [], "negative": []},
            }

        service = SearchEvaluationService(object(), 9, search_fn=_search_fn)
        results = service.evaluate_cases(
            [
                SearchEvaluationCase(
                    name="planner assertion",
                    query="有猫但不是狗",
                    expected_plan={
                        "planner_route": "llm",
                        "semantic_query": "non_empty",
                        "term_groups_contains": {"negative": ["狗"]},
                    },
                )
            ],
            debug=True,
        )

        self.assertFalse(results[0].passed)
        self.assertIn("planner_route", results[0].reason)
        self.assertIn("semantic_query_text expected non-empty", results[0].reason)
        self.assertIn("term_groups.negative", results[0].reason)

    def test_default_baseline_catalog_covers_core_search_slices(self) -> None:
        names = {case.name for case in SEARCH_EVALUATION_BASELINES}
        queries = {case.query for case in SEARCH_EVALUATION_BASELINES}

        self.assertEqual(len(SEARCH_EVALUATION_BASELINES), 6)
        self.assertIn("semantic indoor baseline", names)
        self.assertIn("night scene baseline", names)
        self.assertIn("animal entity baseline", names)
        self.assertIn("group photo baseline", names)
        self.assertIn("weather rain baseline", names)
        self.assertIn("ocr order number baseline", names)
        self.assertIn("室内", queries)
        self.assertIn("夜景", queries)
        self.assertIn("猫", queries)
        self.assertIn("合照", queries)
        self.assertIn("下雨天", queries)
        self.assertIn("订单号", queries)

    def test_planner_debug_catalog_covers_compound_query_planning(self) -> None:
        queries = {case.query for case in SEARCH_PLANNER_DEBUG_EVALUATION_SET}

        self.assertEqual(len(SEARCH_PLANNER_DEBUG_EVALUATION_SET), 6)
        self.assertIn("去年张家口滑雪", queries)
        self.assertIn("去年1月 iPhone 拍的照片", queries)
        self.assertIn("妈妈和孩子的合照", queries)
        self.assertIn("上海下雨天夜景", queries)
        self.assertIn("有猫但不是狗", queries)
        self.assertIn("2024年12月在日本拍的照片", queries)

    def test_evaluate_default_cases_uses_baseline_catalog(self) -> None:
        seen_queries: list[str] = []

        def _search_fn(_db, query, **_kwargs):
            seen_queries.append(query)
            return 0, [], None

        service = SearchEvaluationService(object(), 3, search_fn=_search_fn)
        results = service.evaluate_default_cases(page_size=8)

        self.assertEqual(len(results), len(SEARCH_EVALUATION_BASELINES))
        self.assertEqual(seen_queries, [case.query for case in SEARCH_EVALUATION_BASELINES])

    def test_evaluate_planner_debug_cases_uses_debug_catalog_with_debug_payload(self) -> None:
        calls: list[dict] = []

        def _search_fn(_db, query, **kwargs):
            calls.append({"query": query, **kwargs})
            return 1, [{"photo_id": 101}], {"query": query, "planner_debug": {"planner_route": "llm"}}

        service = SearchEvaluationService(object(), 5, search_fn=_search_fn)
        results = service.evaluate_planner_debug_cases(page_size=4)

        self.assertEqual(len(results), len(SEARCH_PLANNER_DEBUG_EVALUATION_SET))
        self.assertEqual(
            [call["query"] for call in calls],
            [case.query for case in SEARCH_PLANNER_DEBUG_EVALUATION_SET],
        )
        self.assertTrue(all(call["debug"] for call in calls))
        self.assertEqual(results[0].debug_payload, {"query": "去年张家口滑雪", "planner_debug": {"planner_route": "llm"}})


if __name__ == "__main__":
    unittest.main()
