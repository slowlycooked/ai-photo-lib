from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    "caption": "",
    "scene_tags": [],
    "object_tags": [],
    "activity_tags": [],
    "people_count": 0,
    "ocr_text": [],
    "location_clues": [],
    "quality_tags": [],
    "search_keywords": [],
    "confidence": 0.0,
}


def _ensure_list(value: Any) -> list:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def _normalize(data: dict) -> dict:
    result = dict(_DEFAULTS)
    for key, default in _DEFAULTS.items():
        raw = data.get(key, default)
        if isinstance(default, list):
            result[key] = _ensure_list(raw)
        elif isinstance(default, float):
            try:
                result[key] = float(raw)
            except (TypeError, ValueError):
                result[key] = 0.0
        elif isinstance(default, int):
            try:
                result[key] = int(raw)
            except (TypeError, ValueError):
                result[key] = 0
        else:
            result[key] = str(raw) if raw is not None else ""
    return result


def parse_model_json_output(raw_text: str) -> dict:
    """Parse JSON from model output, with progressive fallback strategies."""
    if not raw_text or not raw_text.strip():
        logger.warning("Model returned empty output, using defaults.")
        return dict(_DEFAULTS)

    # Attempt 1: direct parse
    try:
        data = json.loads(raw_text)
        return _normalize(data)
    except json.JSONDecodeError:
        pass

    # Attempt 2: strip Markdown code fences
    stripped = re.sub(r"```(?:json)?\s*", "", raw_text).replace("```", "").strip()
    try:
        data = json.loads(stripped)
        return _normalize(data)
    except json.JSONDecodeError:
        pass

    # Attempt 3: extract first { ... } block
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        fragment = raw_text[start : end + 1]
        try:
            data = json.loads(fragment)
            return _normalize(data)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"Cannot parse model output as JSON. First 300 chars: {raw_text[:300]!r}"
    )
