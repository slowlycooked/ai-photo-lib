from __future__ import annotations

import os
from unittest.mock import patch

import httpx

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")
os.environ.setdefault("EMBEDDING_BASE_URL", "http://127.0.0.1:18085/v1")
os.environ.setdefault("EMBEDDING_MODEL", "embed-model")

from app.services.embedding_client import close_all, embed_texts  # noqa: E402


class _FakeResponse:
    def __init__(self, request: httpx.Request, status_code: int, json_data: dict) -> None:
        self._response = httpx.Response(status_code=status_code, request=request, json=json_data)

    def raise_for_status(self) -> None:
        self._response.raise_for_status()

    def json(self) -> dict:
        return self._response.json()

    @property
    def text(self) -> str:
        return self._response.text

    @property
    def status_code(self) -> int:
        return self._response.status_code


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.post_calls: list[dict] = []
        self.close_calls = 0

    def post(self, url: str, json: dict, headers: dict) -> _FakeResponse:
        self.post_calls.append({"url": url, "json": json, "headers": headers})
        return self.responses.pop(0)

    def close(self) -> None:
        self.close_calls += 1


def _make_response(url: str, status_code: int, embedding: list[float]) -> _FakeResponse:
    request = httpx.Request("POST", url)
    payload = {"data": [{"index": 0, "embedding": embedding}]}
    return _FakeResponse(request, status_code, payload)


def test_embedding_client_reuses_pool_and_closes_all_clients() -> None:
    endpoint = "http://127.0.0.1:18085/v1/embeddings"
    client = _FakeClient([
        _make_response(endpoint, 200, [0.1, 0.2]),
        _make_response(endpoint, 200, [0.1, 0.2]),
    ])

    with patch("app.services.embedding_client.httpx.Client", return_value=client) as client_ctor:
        first = embed_texts(["hello"], endpoint_url=endpoint, api_key="secret", expected_dim=2)
        second = embed_texts(["world"], endpoint_url=endpoint, api_key="secret", expected_dim=2)
        close_all()

    assert first == [[0.1, 0.2]]
    assert second == [[0.1, 0.2]]
    assert client_ctor.call_count == 1
    assert len(client.post_calls) == 2
    assert client.close_calls == 1


def test_embedding_client_retries_transient_http_errors() -> None:
    endpoint = "http://127.0.0.1:18085/v1/embeddings"
    request = httpx.Request("POST", endpoint)
    error_response = httpx.Response(status_code=429, request=request, text="too many requests")
    success = _make_response(endpoint, 200, [0.3, 0.4])
    client = _FakeClient([
        _FakeResponse(request, 429, {"error": "rate limit"}),
        success,
    ])

    with patch("app.services.embedding_client.httpx.Client", return_value=client):
        vectors = embed_texts(["hello"], endpoint_url=endpoint, api_key="secret", expected_dim=2)

    assert vectors == [[0.3, 0.4]]
    assert len(client.post_calls) == 2
