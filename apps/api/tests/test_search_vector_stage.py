from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

from app.services.search.recall_pipeline import run_vector_stage  # noqa: E402
from app.services.search.settings_resolver import SearchSettingsResolver  # noqa: E402
from app.services.search.trace_writer import SearchDebugTraceWriter  # noqa: E402
from app.services.search.types import VectorMatchScores  # noqa: E402


def test_run_vector_stage_uses_two_layer_top_k_strategy() -> None:
    settings = replace(SearchSettingsResolver.defaults(), vector_top_k=50)

    execution_context = SimpleNamespace(
        effective_settings=settings,
        search_query_plan=SimpleNamespace(
            intent="semantic_photo_search",
            original_query="抽象语义查询",
            normalized_query="抽象语义查询",
            semantic_query_text="",
            recommended_profile="default_semantic",
        ),
        project_id=1,
        folder_photo_subquery=None,
        constrained_photo_ids=None,
        page_size=10,
    )

    vector_scores = {
        idx: VectorMatchScores(total_score=float(100 - idx))
        for idx in range(25)
    }

    mock_service = MagicMock()
    mock_service.search.return_value = (vector_scores, "test-embed", "", 0)

    trace: list[dict] = []
    trace_writer = SearchDebugTraceWriter(trace)

    with patch(
        "app.services.search.recall_pipeline.VectorRecallService",
        return_value=mock_service,
    ):
        result = run_vector_stage(
            db=MagicMock(),
            execution_context=execution_context,
            trace_writer=trace_writer,
        )

    assert len(result.vector_scores) == 25
    assert mock_service.search.call_args.kwargs["limit"] == 50

    vector_trace = [item for item in trace if item.get("stage") == "vector_recall"][-1]
    assert vector_trace.get("raw_vector_top_k_per_field") == 50
    assert vector_trace.get("final_vector_top_k") == 50
