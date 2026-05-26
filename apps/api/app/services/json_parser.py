from __future__ import annotations

import json
import logging
import re
from typing import Any

from .concept_normalizer import normalize_concepts_from_payload
from .tag_localization import to_chinese_tag

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
    "semantic_concepts": [],
    "confidence": 0.0,
}

_SCHEMA_ALIASES: dict[str, tuple[str, ...]] = {
    "scene_tags": ("scene_tags", "scene_category", "lifestyle_tags"),
    "object_tags": (
        "object_tags",
        "objects",
        "animals",
        "food_drink",
        "transportation",
        "clothing_accessories",
        "people_tags",
    ),
    "activity_tags": ("activity_tags", "activities"),
    "location_clues": (
        "location_clues",
        "indoor_outdoor",
        "location_type",
        "time_clues",
        "season_weather",
    ),
    "quality_tags": ("quality_tags", "lighting_features", "mood_tags"),
}

_CN_KEYWORD_TAGS: dict[str, tuple[str, str]] = {
    "夜": ("scene_tags", "夜晚"),
    "夜晚": ("scene_tags", "夜晚"),
    "建筑": ("scene_tags", "建筑"),
    "塔": ("object_tags", "塔"),
    "楼": ("object_tags", "楼"),
    "传统": ("quality_tags", "传统"),
    "清晰": ("quality_tags", "清晰"),
    "高清": ("quality_tags", "高清"),
    "划船": ("activity_tags", "划船"),
    "泛舟": ("activity_tags", "划船"),
    "游船": ("activity_tags", "划船"),
    "皮划艇": ("activity_tags", "皮划艇"),
}

_EN_KEYWORD_TAGS: dict[str, tuple[str, str]] = {
    "night": ("scene_tags", "夜晚"),
    "architecture": ("scene_tags", "建筑"),
    "tower": ("object_tags", "塔"),
    "building": ("object_tags", "楼"),
    "traditional": ("quality_tags", "传统"),
    "high quality": ("quality_tags", "高清"),
    "clear": ("quality_tags", "清晰"),
    "boating": ("activity_tags", "划船"),
    "rowing": ("activity_tags", "划船"),
    "sailing": ("activity_tags", "开船"),
    "kayaking": ("activity_tags", "皮划艇"),
    "canoeing": ("activity_tags", "独木舟"),
    "boat": ("object_tags", "船"),
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


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if text not in target:
            target.append(text)


def _localize_tag_list(values: list[str]) -> list[str]:
    localized: list[str] = []
    for value in values:
        zh = to_chinese_tag(value)
        if zh and zh not in localized:
            localized.append(zh)
    return localized


def _localize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    localized = dict(payload)
    tag_fields = (
        "scene_tags",
        "object_tags",
        "activity_tags",
        "quality_tags",
        "location_clues",
        "search_keywords",
        "semantic_concepts",
    )
    for field in tag_fields:
        localized[field] = _localize_tag_list(_ensure_list(localized.get(field)))

    merged_keywords: list[str] = []
    _append_unique(merged_keywords, localized.get("search_keywords", []))
    for field in ("scene_tags", "object_tags", "activity_tags", "quality_tags", "location_clues"):
        _append_unique(merged_keywords, localized.get(field, []))
    localized["search_keywords"] = merged_keywords
    return localized


def _to_schema_payload(data: dict) -> dict:
    """Map model-specific keys into the stable analysis schema."""
    payload: dict[str, Any] = {}

    if "caption" in data:
        payload["caption"] = data.get("caption")
    if "people_count" in data:
        payload["people_count"] = data.get("people_count")
    if "confidence" in data:
        payload["confidence"] = data.get("confidence")
    if "ocr_text" in data:
        payload["ocr_text"] = data.get("ocr_text")

    for schema_key, aliases in _SCHEMA_ALIASES.items():
        merged: list[str] = []
        for alias in aliases:
            _append_unique(merged, _ensure_list(data.get(alias)))
        if merged:
            payload[schema_key] = merged

    merged_search_keywords: list[str] = []
    _append_unique(merged_search_keywords, _ensure_list(data.get("search_keywords")))
    _append_unique(merged_search_keywords, _ensure_list(payload.get("scene_tags")))
    _append_unique(merged_search_keywords, _ensure_list(payload.get("object_tags")))
    _append_unique(merged_search_keywords, _ensure_list(payload.get("activity_tags")))
    _append_unique(merged_search_keywords, _ensure_list(payload.get("location_clues")))
    if merged_search_keywords:
        payload["search_keywords"] = merged_search_keywords

    return payload


def _enrich_search_keywords(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(payload)
    merged_search_keywords: list[str] = []
    semantic_concepts: list[str] = []

    _append_unique(merged_search_keywords, _ensure_list(enriched.get("search_keywords")))
    for field in (
        "scene_tags",
        "object_tags",
        "activity_tags",
        "quality_tags",
        "location_clues",
    ):
        _append_unique(merged_search_keywords, _ensure_list(enriched.get(field)))

    normalized = normalize_concepts_from_payload(
        caption=enriched.get("caption"),
        scene_tags=_ensure_list(enriched.get("scene_tags")),
        object_tags=_ensure_list(enriched.get("object_tags")),
        activity_tags=_ensure_list(enriched.get("activity_tags")),
        search_keywords=_ensure_list(enriched.get("search_keywords")),
        location_clues=_ensure_list(enriched.get("location_clues")),
        raw_result=enriched if isinstance(enriched, dict) else None,
        people_count=enriched.get("people_count"),
    )
    semantic_terms = list(normalized.semantic_entities) + list(normalized.semantic_concepts)

    _append_unique(semantic_concepts, _ensure_list(enriched.get("semantic_concepts")))
    _append_unique(semantic_concepts, semantic_terms)
    if semantic_concepts:
        enriched["semantic_concepts"] = semantic_concepts

    _append_unique(merged_search_keywords, semantic_terms)

    if merged_search_keywords:
        enriched["search_keywords"] = merged_search_keywords
    return enriched


def validate_image_analysis_result(data: dict) -> dict:
    """Validate/normalize parsed image-analysis payload into required schema."""
    if not isinstance(data, dict):
        raise ValueError("Model output root must be a JSON object")
    return _normalize(_enrich_search_keywords(_localize_payload(_to_schema_payload(data))))


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s in ("{", "}"):
            continue
        if s.startswith("- "):
            continue
        return s
    return ""


def _extract_partial_json_pairs(raw_text: str) -> dict[str, Any]:
    """Recover key/value pairs from truncated JSON-like output.

    Example input often ends with an unclosed quote/bracket due to token limit.
    We keep only lines that can be parsed independently.
    """
    recovered: dict[str, Any] = {}
    for line in raw_text.splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped or stripped in ("{", "}"):
            continue
        m = re.match(r'^"(?P<key>[^"]+)"\s*:\s*(?P<value>.+)$', stripped)
        if not m:
            continue

        key = m.group("key")
        value_text = m.group("value").strip()
        if not value_text:
            continue

        # Ignore unfinished scalar/list values produced by truncated output.
        if value_text.startswith('"') and not re.match(r'^"(?:[^"\\]|\\.)*"$', value_text):
            continue
        if value_text.startswith("[") and not value_text.endswith("]"):
            continue
        if value_text.startswith("{") and not value_text.endswith("}"):
            continue

        try:
            recovered[key] = json.loads(value_text)
        except json.JSONDecodeError:
            continue

    return recovered


def _infer_people_count(text: str) -> int:
    lowered = text.lower()
    if "无人" in text or "没有人" in text or "no people" in lowered:
        return 0

    m = re.search(r"people_count\s*[:：]\s*(\d+)", lowered)
    if m:
        return int(m.group(1))

    m = re.search(r"(?:人数|人们数量)\s*[:：]?\s*(\d+)", text)
    if m:
        return int(m.group(1))

    return 0


def _infer_confidence(text: str) -> float:
    lowered = text.lower()
    m = re.search(r"confidence\s*[:：]\s*([0-9]+(?:\.[0-9]+)?%?)", lowered)
    if m:
        return _ensure_float(m.group(1))

    m = re.search(r"置信度\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?%?)", text)
    if m:
        return _ensure_float(m.group(1))

    if "较高" in text or "高" in text:
        return 0.75
    if "较低" in text or "低" in text:
        return 0.35
    return 0.5


def _extract_tags_from_keywords(text: str) -> dict[str, list[str]]:
    lowered = text.lower()
    tags: dict[str, list[str]] = {
        "scene_tags": [],
        "object_tags": [],
        "activity_tags": [],
        "location_clues": [],
        "quality_tags": [],
        "search_keywords": [],
    }

    for keyword, (bucket, tag) in _CN_KEYWORD_TAGS.items():
        if keyword in text and tag not in tags[bucket]:
            tags[bucket].append(tag)

    for keyword, (bucket, tag) in _EN_KEYWORD_TAGS.items():
        if keyword in lowered and tag not in tags[bucket]:
            tags[bucket].append(tag)

    if "城市" in text or "city" in lowered:
        tags["location_clues"].append("城市")

    for bucket in ("scene_tags", "object_tags", "location_clues"):
        for tag in tags[bucket]:
            if tag not in tags["search_keywords"]:
                tags["search_keywords"].append(tag)

    return tags


def _build_fallback_from_plain_text(raw_text: str) -> dict:
    """Build a best-effort schema payload when model output has no JSON."""
    caption = _first_nonempty_line(raw_text)
    tags = _extract_tags_from_keywords(raw_text)
    result = {
        "caption": caption,
        "scene_tags": tags["scene_tags"],
        "object_tags": tags["object_tags"],
        "activity_tags": tags["activity_tags"],
        "people_count": _infer_people_count(raw_text),
        "ocr_text": [],
        "location_clues": tags["location_clues"],
        "quality_tags": tags["quality_tags"],
        "search_keywords": tags["search_keywords"],
        "confidence": _infer_confidence(raw_text),
    }
    return validate_image_analysis_result(result)


def parse_model_json_output(raw_text: str, strategy: str = "auto_extract") -> dict:
    """Parse JSON from model output, with selectable fallback strategies.

    Supported strategies:
    - strict_json: only direct JSON parsing
    - strip_markdown: direct parse + markdown fence stripping
    - auto_extract: full fallback pipeline including object extraction (default)
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Model returned empty output; cannot parse JSON.")

    # Some models occasionally prepend BOM-like markers.
    raw_text = raw_text.strip().lstrip("\ufeff")

    # Attempt 1: direct parse
    try:
        data = json.loads(raw_text)
        return validate_image_analysis_result(data)
    except json.JSONDecodeError:
        pass

    if strategy == "strict_json":
        raise ValueError(
            "Cannot parse model output as strict JSON. "
            f"First 300 chars: {raw_text[:300]!r}. "
            f"Raw output:\n{raw_text}"
        )

    # Attempt 2: strip Markdown code fences
    stripped = re.sub(r"```(?:json)?\s*", "", raw_text).replace("```", "").strip()
    try:
        data = json.loads(stripped)
        return validate_image_analysis_result(data)
    except json.JSONDecodeError:
        pass

    if strategy == "strip_markdown":
        raise ValueError(
            "Cannot parse model output as JSON after markdown stripping. "
            f"First 300 chars: {raw_text[:300]!r}. "
            f"Raw output:\n{raw_text}"
        )

    # Attempt 3: extract first { ... } block
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        fragment = raw_text[start : end + 1]
        try:
            data = json.loads(fragment)
            return validate_image_analysis_result(data)
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
            return validate_image_analysis_result(data)

    # Attempt 5: recover parseable key/value lines from truncated JSON-like text.
    partial = _extract_partial_json_pairs(raw_text)
    if partial:
        logger.warning(
            "Model output JSON was truncated; recovered partial key/value fields."
        )
        return validate_image_analysis_result(partial)

    if strategy == "auto_extract":
        logger.warning(
            "Model output had no decodable JSON; using plain-text fallback extraction."
        )
        return _build_fallback_from_plain_text(raw_text)

    raise ValueError(
        "Cannot parse model output as JSON. "
        f"First 300 chars: {raw_text[:300]!r}. "
        f"Raw output:\n{raw_text}"
    )
