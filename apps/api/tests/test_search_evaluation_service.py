from __future__ import annotations

import unittest

from app.services.search.search_evaluation_catalog import SEARCH_EVALUATION_BASELINES
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

    def test_evaluate_default_cases_uses_baseline_catalog(self) -> None:
        seen_queries: list[str] = []

        def _search_fn(_db, query, **_kwargs):
            seen_queries.append(query)
            return 0, [], None

        service = SearchEvaluationService(object(), 3, search_fn=_search_fn)
        results = service.evaluate_default_cases(page_size=8)

        self.assertEqual(len(results), len(SEARCH_EVALUATION_BASELINES))
        self.assertEqual(seen_queries, [case.query for case in SEARCH_EVALUATION_BASELINES])


if __name__ == "__main__":
    unittest.main()
