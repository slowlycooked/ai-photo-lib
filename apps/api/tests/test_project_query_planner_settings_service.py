from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")
os.environ.setdefault("QUERY_PLANNER_BASE_URL", "http://127.0.0.1:18084/v1")
os.environ.setdefault("QUERY_PLANNER_ALIAS", "qwen3-4b-query-planner")

from app.services.project_query_planner_settings_service import (  # noqa: E402
    _default_query_planner_model_name,
    get_project_query_planner_settings,
    resolve_query_planner_settings,
)


def test_resolve_query_planner_settings_uses_table_row_first() -> None:
    row = SimpleNamespace(
        enabled=True,
        provider="llama-server",
        endpoint_url="http://127.0.0.1:18084/v1/chat/completions",
        api_key="abc",
        model_name="qwen3-4b-query-planner",
        temperature=0.0,
        top_p=0.8,
        max_tokens=700,
        timeout_seconds=20,
        json_parse_strategy="strict_json_then_extract",
        planner_version="llm_query_planner_v1",
        prompt_template="tmpl",
        system_prompt="sys",
        fallback_mode="rule_fallback",
    )

    with patch(
        "app.services.project_query_planner_settings_service.get_project_query_planner_settings",
        return_value=row,
    ):
        resolved = resolve_query_planner_settings(MagicMock(), 1, search_quality_settings={
            "query_planner_enabled": False,
            "query_planner_model_name": "legacy-model",
        })

    assert resolved["enabled"] is True
    assert resolved["model_name"] == "qwen3-4b-query-planner"
    assert resolved["endpoint_url"].endswith("/chat/completions")


def test_resolve_query_planner_settings_preserves_explicit_blank_runtime_fields() -> None:
    row = SimpleNamespace(
        enabled=True,
        provider="llama-server",
        endpoint_url=None,
        api_key="",
        model_name="",
        temperature=0.0,
        top_p=0.8,
        max_tokens=700,
        timeout_seconds=20,
        json_parse_strategy="strict_json_then_extract",
        planner_version="llm_query_planner_v1",
        prompt_template="",
        system_prompt="",
        fallback_mode="rule_fallback",
    )

    with patch(
        "app.services.project_query_planner_settings_service.get_project_query_planner_settings",
        return_value=row,
    ):
        resolved = resolve_query_planner_settings(MagicMock(), 1, search_quality_settings=None)

    assert resolved["endpoint_url"] == ""
    assert resolved["model_name"] == ""


def test_resolve_query_planner_settings_falls_back_to_legacy_json() -> None:
    with patch(
        "app.services.project_query_planner_settings_service.get_project_query_planner_settings",
        return_value=None,
    ):
        resolved = resolve_query_planner_settings(
            MagicMock(),
            1,
            search_quality_settings={
                "query_planner_enabled": True,
                "query_planner_provider": "llama-server",
                "query_planner_endpoint_url": "http://127.0.0.1:18084/v1/chat/completions",
                "query_planner_model_name": "qwen3-4b-query-planner",
                "query_planner_temperature": 0,
                "query_planner_top_p": 0.8,
                "query_planner_max_tokens": 700,
            },
        )

    assert resolved["enabled"] is True
    assert resolved["model_name"] == "qwen3-4b-query-planner"
    assert resolved["max_tokens"] == 700


def test_resolve_query_planner_settings_defaults_from_env() -> None:
    with patch(
        "app.services.project_query_planner_settings_service.get_project_query_planner_settings",
        return_value=None,
    ):
        resolved = resolve_query_planner_settings(MagicMock(), 1, search_quality_settings=None)

    assert resolved["enabled"] is True
    assert resolved["endpoint_url"] == "http://127.0.0.1:18084/v1"
    assert resolved["model_name"] == _default_query_planner_model_name()


def test_get_project_query_planner_settings_rolls_back_failed_transaction() -> None:
    db = MagicMock()
    db.query.side_effect = SQLAlchemyError("missing table")

    resolved = get_project_query_planner_settings(db, 1)

    assert resolved is None
    db.rollback.assert_called_once()
