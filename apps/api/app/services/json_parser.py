from __future__ import annotations

import json
import logging
import re
from typing import Any
from pathlib import Path
from typing import Tuple

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


def _ensure_int(value: Any) -> int:
    if isinstance(value, list):
        if not value:
            return 0
        return _ensure_int(value[0])
    if isinstance(value, str):
        value = value.strip()
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ensure_float(value: Any) -> float:
    if isinstance(value, list):
        if not value:
            return 0.0
        return _ensure_float(value[0])
    if isinstance(value, str):
        text = value.strip().replace("%", "")
        try:
            num = float(text)
        except ValueError:
            return 0.0
        if "%" in value:
            num = num / 100.0
        return max(0.0, min(1.0, num))
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _normalize(data: dict) -> dict:
    result = dict(_DEFAULTS)
    for key, default in _DEFAULTS.items():
        raw = data.get(key, default)
        if isinstance(default, list):
            result[key] = _ensure_list(raw)
        elif isinstance(default, float):
            result[key] = _ensure_float(raw)
        elif isinstance(default, int):
            result[key] = _ensure_int(raw)
        else:
            result[key] = str(raw) if raw is not None else ""
    return result


def build_relative_paths(library_path: str, entry: Path) -> Tuple[str, str]:
    """
    计算照片的 relative_path 和 folder_path
    """
    # Ensure library_path is a Path object for relative_to
    lib_path = Path(library_path).resolve()
    entry_path = Path(entry).resolve()
    
    rel_path = str(entry_path.relative_to(lib_path))
    if "/" in rel_path:
        folder_path = rel_path.rsplit("/", 1)[0]
    else:
        folder_path = ""
    return rel_path, folder_path


def parse_model_json_output(raw_text: str) -> dict:
    """Parse JSON from model output, with progressive fallback strategies."""
    if not raw_text or not raw_text.strip():
        logger.warning("Model returned empty output, using defaults.")
        return dict(_DEFAULTS)

    # Some models occasionally prepend BOM-like markers.
    raw_text = raw_text.strip().lstrip("\ufeff")

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

    # Attempt 4: scan for any decodable JSON object in the text and use
    # the first dict object encountered.
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw_text):
        idx = match.start()
        try:
            data, _ = decoder.raw_decode(raw_text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return _normalize(data)

    raise ValueError(
        "Cannot parse model output as JSON. "
        f"First 300 chars: {raw_text[:300]!r}. "
        f"Raw output:\n{raw_text}"
    )

