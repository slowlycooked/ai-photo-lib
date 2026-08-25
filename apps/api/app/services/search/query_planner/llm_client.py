"""HTTP client for OpenAI-compatible query planner LLM calls."""
from __future__ import annotations

import threading
from typing import Any, Optional

import httpx


class QueryPlannerClientError(RuntimeError):
    """Raised when query planner chat completion call fails."""


_CLIENT_LOCK = threading.Lock()
_CLIENTS_BY_TIMEOUT: dict[float, httpx.Client] = {}


def _get_http_client(timeout_seconds: int) -> httpx.Client:
    timeout_value = float(max(1, timeout_seconds))
    with _CLIENT_LOCK:
        client = _CLIENTS_BY_TIMEOUT.get(timeout_value)
        if client is not None:
            return client
        client = httpx.Client(timeout=timeout_value)
        _CLIENTS_BY_TIMEOUT[timeout_value] = client
        return client


def normalize_chat_url(endpoint_url: str) -> str:
    url = str(endpoint_url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return url


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "".join(parts)
    return ""


def call_chat_completion(
    *,
    endpoint_url: str,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    timeout_seconds: int,
    json_schema: Optional[dict[str, Any]] = None,
) -> str:
    """Call OpenAI-compatible chat completions and return response text."""
    url = normalize_chat_url(endpoint_url)
    if not url:
        raise QueryPlannerClientError("Missing query planner endpoint URL")
    if not model_name.strip():
        raise QueryPlannerClientError("Missing query planner model name")

    payload: dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(temperature),
        "top_p": float(top_p),
        "max_tokens": int(max_tokens),
        "stream": False,
        "response_format": (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "query_plan_v2",
                    "strict": True,
                    "schema": json_schema,
                },
            }
            if json_schema is not None
            else {"type": "json_object"}
        ),
        "chat_template_kwargs": {"enable_thinking": False},
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    client = _get_http_client(timeout_seconds)
    try:
        response = client.post(url, json=payload, headers=headers)
        if response.status_code == 400:
            body = response.text.lower()
            if json_schema is not None and (
                "json_schema" in body or "response_format" in body
            ):
                compat_payload = dict(payload)
                compat_payload["response_format"] = {"type": "json_object"}
                response = client.post(url, json=compat_payload, headers=headers)
                body = response.text.lower()
            if response.status_code == 400 and "response_format" in body:
                compat_payload = dict(payload)
                compat_payload.pop("response_format", None)
                response = client.post(url, json=compat_payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise QueryPlannerClientError(
            f"Query planner request timed out after {max(1, timeout_seconds)}s"
        ) from exc
    except httpx.RequestError as exc:
        raise QueryPlannerClientError(f"Query planner request failed: {exc}") from exc
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise QueryPlannerClientError(
            f"Query planner HTTP {response.status_code}: {response.text[:600]}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise QueryPlannerClientError("Query planner response is not valid JSON") from exc

    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise QueryPlannerClientError("Query planner response missing choices")
    first = choices[0] if isinstance(choices[0], dict) else {}
    message = first.get("message") if isinstance(first, dict) else {}
    if not isinstance(message, dict):
        raise QueryPlannerClientError("Query planner response missing message payload")
    text = extract_message_text(message)
    if not text.strip():
        raise QueryPlannerClientError("Query planner returned empty content")
    return text
