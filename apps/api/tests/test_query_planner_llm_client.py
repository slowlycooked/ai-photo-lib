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
    mock_client.post.side_effect = httpx.ReadTimeout(
        "timed out",
        request=httpx.Request("POST", "http://127.0.0.1:18084/v1/chat/completions"),
    )

    with patch(
        "app.services.search.query_planner.llm_client._get_http_client",
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


def test_call_chat_completion_uses_json_schema_and_disables_thinking() -> None:
    mock_client = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": '{"version":"2"}'}}]
    }
    mock_client.post.return_value = response
    schema = {"type": "object", "properties": {"version": {"const": "2"}}}

    with patch(
        "app.services.search.query_planner.llm_client._get_http_client",
        return_value=mock_client,
    ):
        result = call_chat_completion(
            endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
            api_key="test-key",
            model_name="qwen3-8b-query-planner",
            system_prompt="system",
            user_prompt="user",
            temperature=0,
            top_p=0.8,
            max_tokens=512,
            timeout_seconds=5,
            json_schema=schema,
        )

    assert result == '{"version":"2"}'
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["schema"] == schema
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
