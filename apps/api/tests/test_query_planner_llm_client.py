from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.search.query_planner.llm_client import (
    QueryPlannerClientError,
    call_chat_completion,
)


def test_call_chat_completion_wraps_timeout_as_query_planner_client_error() -> None:
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = None
    mock_client.post.side_effect = httpx.ReadTimeout(
        "timed out",
        request=httpx.Request("POST", "http://127.0.0.1:18084/v1/chat/completions"),
    )

    with patch(
        "app.services.search.query_planner.llm_client.httpx.Client",
        return_value=mock_client,
    ):
        with pytest.raises(QueryPlannerClientError, match="timed out"):
            call_chat_completion(
                endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
                api_key="test-key",
                model_name="qwen3-4b-query-planner",
                system_prompt="system",
                user_prompt="user",
                temperature=0,
                top_p=0.8,
                max_tokens=700,
                timeout_seconds=5,
            )