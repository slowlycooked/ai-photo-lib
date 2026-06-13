from __future__ import annotations

import threading
import time
import logging
from typing import Any

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_CLIENT_LOCK = threading.Lock()
_CLIENTS_BY_KEY: dict[tuple[str, float, bool], httpx.Client] = {}


class EmbeddingRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        code: str | None = None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


def _embeddings_url_from_endpoint(endpoint_url: str) -> str:
    url = endpoint_url.strip().rstrip("/")
    if not url:
        raise EmbeddingRequestError("Missing embedding endpoint URL", retryable=False, code="missing_endpoint")

    if url.endswith("/embeddings"):
        return url
    if url.endswith("/chat/completions"):
        return f"{url[:-len('/chat/completions')]}/embeddings"
    if url.endswith("/completions"):
        return f"{url[:-len('/completions')]}/embeddings"
    if url.endswith("/v1"):
        return f"{url}/embeddings"
    return f"{url}/v1/embeddings"


def _default_model() -> str:
    return settings.embedding_model or settings.openai_model


def _default_api_key() -> str:
    return settings.embedding_api_key or settings.openai_api_key


def _normalize_endpoint_url(endpoint_url: str | None = None) -> str:
    if endpoint_url and endpoint_url.strip():
        return _embeddings_url_from_endpoint(endpoint_url)

    base = (settings.embedding_base_url or settings.openai_base_url).strip()
    return _embeddings_url_from_endpoint(base)


def _client_key(endpoint_url: str, timeout_seconds: int, api_key: str | None) -> tuple[str, float, bool]:
    return (
        endpoint_url.strip().rstrip("/"),
        float(max(1, timeout_seconds)),
        bool((api_key or "").strip()),
    )


def _get_http_client(endpoint_url: str, timeout_seconds: int, api_key: str | None) -> httpx.Client:
    key = _client_key(endpoint_url, timeout_seconds, api_key)
    with _CLIENT_LOCK:
        client = _CLIENTS_BY_KEY.get(key)
        if client is not None:
            return client
        client = httpx.Client(
            timeout=float(max(1, timeout_seconds)),
            limits=httpx.Limits(
                max_keepalive_connections=8,
                max_connections=16,
                keepalive_expiry=60.0,
            ),
        )
        _CLIENTS_BY_KEY[key] = client
        return client


def close_all() -> None:
    with _CLIENT_LOCK:
        clients = list(_CLIENTS_BY_KEY.values())
        _CLIENTS_BY_KEY.clear()
    for client in clients:
        client.close()


def embed_texts(
    texts: list[str],
    *,
    model: str | None = None,
    endpoint_url: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int | None = None,
    expected_dim: int | None = None,
) -> list[list[float]]:
    clean_texts = [t.strip() for t in texts if t and t.strip()]
    if not clean_texts:
        return []

    used_model = model or _default_model()
    if not used_model:
        raise EmbeddingRequestError("Missing embedding model configuration", retryable=False, code="missing_model")

    url = _normalize_endpoint_url(endpoint_url)
    used_api_key = api_key or _default_api_key()
    used_timeout = timeout_seconds if timeout_seconds is not None else settings.embedding_timeout_seconds
    headers = {
        "Authorization": f"Bearer {used_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": used_model,
        "input": clean_texts,
    }

    client = _get_http_client(url, used_timeout, used_api_key)
    response = None
    try:
        for attempt in range(3):
            try:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retryable = status >= 500 or status == 429
                if retryable and attempt < 2:
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise EmbeddingRequestError(
                    f"Embedding API returned HTTP {status}: {exc.response.text[:500]}",
                    retryable=retryable,
                    code=f"http_{status}",
                ) from exc
    except httpx.ConnectError as exc:
        raise EmbeddingRequestError(
            f"Cannot connect to embedding API at {url}",
            retryable=True,
            code="connect_error",
        ) from exc
    except httpx.TimeoutException as exc:
        raise EmbeddingRequestError(
            "Embedding API request timed out",
            retryable=True,
            code="timeout",
        ) from exc
    if response is None:
        raise EmbeddingRequestError(
            "Embedding API returned no response",
            retryable=False,
            code="empty_response",
        )

    data: dict[str, Any] = response.json()
    items = data.get("data") or []
    embeddings: list[list[float]] = []

    for item in sorted(items, key=lambda x: x.get("index", 0)):
        emb = item.get("embedding")
        if not isinstance(emb, list):
            raise EmbeddingRequestError(
                "Embedding response item missing embedding list",
                retryable=False,
                code="invalid_payload",
            )
        embeddings.append([float(x) for x in emb])

    if len(embeddings) != len(clean_texts):
        raise EmbeddingRequestError(
            f"Embedding response count mismatch: expected {len(clean_texts)}, got {len(embeddings)}",
            retryable=False,
            code="count_mismatch",
        )

    dim = expected_dim or settings.embedding_dimension
    for emb in embeddings:
        if len(emb) != dim:
            raise EmbeddingRequestError(
                f"Embedding dimension mismatch: expected {dim}, got {len(emb)}",
                retryable=False,
                code="dimension_mismatch",
            )

    return embeddings


def embed_text(
    text: str,
    *,
    model: str | None = None,
    endpoint_url: str | None = None,
    api_key: str | None = None,
    timeout_seconds: int | None = None,
    expected_dim: int | None = None,
) -> list[float]:
    vectors = embed_texts(
        [text],
        model=model,
        endpoint_url=endpoint_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        expected_dim=expected_dim,
    )
    if not vectors:
        raise EmbeddingRequestError("No embedding returned", retryable=False, code="empty_result")
    return vectors[0]
