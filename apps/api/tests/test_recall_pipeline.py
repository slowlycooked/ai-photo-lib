from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.embedding_client import EmbeddingRequestError  # noqa: E402
from app.services.query_understanding_service import SearchQueryPlan  # noqa: E402
from app.services.search.execution_context import SearchExecutionContext  # noqa: E402
from app.services.search.people_query_resolver import (  # noqa: E402
    PeopleQueryResolution,
    ResolvedPersonRef,
)
from app.services.search.recall_pipeline import (  # noqa: E402
    merge_keyword_with_aux_candidates,
    run_metadata_stage,
    run_people_stage,
    run_vector_stage,
)
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.search.trace_writer import SearchDebugTraceWriter  # noqa: E402
from app.services.search.types import SearchCandidate  # noqa: E402


class RecallPipelineStageTest(unittest.TestCase):
    def _build_context(
        self,
        *,
        project_id: int = 1,
        metadata_filters: dict | None = None,
        metadata_filter_active: bool = False,
        metadata_only_requested: bool = False,
        metadata_only_allowed: bool = True,
        people_resolution: PeopleQueryResolution | None = None,
    ) -> SearchExecutionContext:
        query_plan = SearchQueryPlan(
            original_query="测试",
            normalized_query="测试",
            exact_terms=["测试"],
            intent="semantic_photo_search",
        )
        resolution = people_resolution or PeopleQueryResolution(
            query="测试",
            residual_query="测试",
            people_filter_mode="none",
            matched_people=[],
        )
        return SearchExecutionContext(
            project_id=project_id,
            effective_settings=SearchSettingsResolver.defaults(),
            query_plan=query_plan,
            search_query_plan=query_plan,
            people_resolution=resolution,
            people_query_plan={},
            effective_mode="hybrid",
            metadata_filters=metadata_filters or {},
            metadata_only_requested=metadata_only_requested,
            metadata_only_allowed=metadata_only_allowed,
            metadata_filter_skipped_reason="not_skipped",
            metadata_filter_active=metadata_filter_active,
            trace=[],
            folder_photo_subquery=None,
        )

    def test_metadata_only_stage_returns_terminal_candidates(self) -> None:
        trace: list[dict] = []
        writer = SearchDebugTraceWriter(trace)
        context = self._build_context(
            metadata_filters={"metadata_only": True, "year": 2024},
            metadata_filter_active=True,
            metadata_only_requested=True,
            metadata_only_allowed=True,
        )

        with patch(
            "app.services.search.recall_pipeline.MetadataRecallService.search",
            return_value=[SearchCandidate(photo_id=7, final_score=0.8)],
        ):
            result = run_metadata_stage(
                db=MagicMock(),
                execution_context=context,
                trace_writer=writer,
            )

        self.assertIsNotNone(result.metadata_only_candidates)
        assert result.metadata_only_candidates is not None
        self.assertEqual(result.metadata_only_candidates[0].photo_id, 7)
        self.assertEqual(trace[-1]["stage"], "metadata_filter")
        self.assertEqual(trace[-1]["path"], "metadata-only")

    def test_people_stage_people_only_returns_candidates(self) -> None:
        trace: list[dict] = []
        writer = SearchDebugTraceWriter(trace)
        people_resolution = PeopleQueryResolution(
            query="小明",
            residual_query="",
            people_filter_mode="any",
            matched_people=[
                ResolvedPersonRef(
                    person_id=1,
                    display_name="小明",
                    normalized_name="xiaoming",
                    matched_term="小明",
                )
            ],
        )
        context = self._build_context(people_resolution=people_resolution)
        people_candidates = [
            SearchCandidate(
                photo_id=9,
                people_score=1.0,
                people_rank=1,
                people_explain={"matched_people": [{"person_id": 1}]},
            )
        ]
        fake_recall_result = SimpleNamespace(
            candidates=people_candidates,
            matched_person_ids=[1],
            photo_ids=[9],
        )

        with patch(
            "app.services.search.recall_pipeline.PeopleRecallService.recall",
            return_value=fake_recall_result,
        ):
            result = run_people_stage(
                db=MagicMock(),
                execution_context=context,
                trace_writer=writer,
            )

        self.assertIsNotNone(result.people_only_candidates)
        assert result.people_only_candidates is not None
        self.assertEqual(result.people_only_candidates[0].photo_id, 9)
        self.assertEqual(result.matched_person_ids, [1])
        self.assertEqual(trace[-1]["stage"], "people_recall")

    def test_people_stage_boost_mode_does_not_constrain_followup_recall(self) -> None:
        trace: list[dict] = []
        writer = SearchDebugTraceWriter(trace)
        people_resolution = PeopleQueryResolution(
            query="爸爸",
            residual_query="",
            people_filter_mode="boost",
            matched_people=[
                ResolvedPersonRef(
                    person_id=1,
                    display_name="爸爸",
                    normalized_name="爸爸",
                    matched_term="爸爸",
                )
            ],
        )
        context = self._build_context(people_resolution=people_resolution)
        people_candidates = [
            SearchCandidate(
                photo_id=9,
                people_score=1.0,
                people_rank=1,
                people_explain={"matched_people": [{"person_id": 1}]},
            )
        ]
        fake_recall_result = SimpleNamespace(
            candidates=people_candidates,
            matched_person_ids=[1],
            photo_ids=[9],
        )

        with patch(
            "app.services.search.recall_pipeline.PeopleRecallService.recall",
            return_value=fake_recall_result,
        ):
            result = run_people_stage(
                db=MagicMock(),
                execution_context=context,
                trace_writer=writer,
            )

        self.assertIsNone(result.constrained_photo_ids)
        self.assertIsNone(result.people_only_candidates)
        self.assertEqual(result.people_results[0].photo_id, 9)
        self.assertEqual(trace[-1]["people_filter_mode"], "boost")

    def test_vector_stage_reports_fallback_on_embedding_error(self) -> None:
        trace: list[dict] = []
        writer = SearchDebugTraceWriter(trace)
        context = self._build_context()
        context.search_query_plan = SearchQueryPlan(
            original_query="海边",
            normalized_query="海边",
            exact_terms=["海边"],
            intent="semantic_photo_search",
        )

        with patch(
            "app.services.search.recall_pipeline.VectorRecallService.search",
            side_effect=EmbeddingRequestError("embedding down"),
        ):
            result = run_vector_stage(
                db=MagicMock(),
                execution_context=context,
                trace_writer=writer,
            )

        self.assertEqual(result.vector_scores, {})
        self.assertIsNotNone(result.error)
        self.assertIn("embedding down", result.fallback_reason)
        self.assertTrue(trace[-1]["fallback"])

    def test_merge_keyword_with_aux_candidates_accepts_scalar_keyword_explain_values(self) -> None:
        keyword_results = [
            SearchCandidate(
                photo_id=11,
                keyword_score=0.2,
                matched_tags=["动物"],
                match_source=["keyword"],
                keyword_explain={"semantic_concepts": ["动物"]},
                term_level_hits={"exact": ["猫"]},
            )
        ]
        aux_results = [
            SearchCandidate(
                photo_id=11,
                keyword_score=0.6,
                matched_tags=["猫"],
                match_source=["concept"],
                keyword_explain={
                    "semantic_entities": ["猫"],
                    "concept_term_coverage": 0.5,
                },
                term_level_hits={"strong": ["猫"]},
            )
        ]

        merged = merge_keyword_with_aux_candidates(
            keyword_results,
            aux_results,
            aux_source="concept",
        )

        self.assertEqual(len(merged), 1)
        merged_candidate = merged[0]
        self.assertEqual(merged_candidate.photo_id, 11)
        self.assertEqual(merged_candidate.keyword_score, 0.6)
        self.assertIn("concept", merged_candidate.match_source)
        self.assertEqual(
            merged_candidate.keyword_explain.get("concept_term_coverage"),
            [0.5],
        )


if __name__ == "__main__":
    unittest.main()
