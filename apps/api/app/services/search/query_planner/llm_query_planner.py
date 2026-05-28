"""LLM-first query planner with deterministic rule fallback."""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from typing import Callable, Optional

from ....config import settings as global_settings
from ...query_understanding_service import SearchQueryPlan
from ..types import EffectiveSearchSettings
from .fallback import build_fallback_plan
from .llm_client import QueryPlannerClientError, call_chat_completion
from .mapper import planner_output_to_query_plan
from .schema import LLMQueryPlannerOutput

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "你是 ai-photo-lib 的照片搜索 Query Planner。"
    "你的任务是把用户自然语言查询转换成严格 JSON 搜索计划。"
    "不能输出解释、Markdown、代码块或 JSON 之外的任何文本。"
)

_DEFAULT_USER_PROMPT_TEMPLATE = """请为以下照片搜索请求生成 JSON 搜索计划。

用户 query:
{{query}}

输出语言: zh-CN
当前日期: {{today}}
项目 ID: {{project_id}}

必须输出 JSON，且包含以下字段：
intent, search_mode, normalized_query, semantic_query_text,
terms(exact, expanded, support, broad, negative),
facets(object, scene, activity, people, weather, time, location),
filters(people_count_min, people_count_max, has_people, has_animals, indoor_outdoor, weather, time_of_day),
metadata_filters(year, month, date_from, date_to, season, has_gps, camera_make, camera_model, iso_min, iso_max, place_terms, metadata_only, matched_metadata_terms),
concept_terms, semantic_tags, core_facets,
core_facet_evidence(positive_terms, negative_terms),
query_constraints(requires_visual_evidence, allow_weak_only_match, min_evidence_level, query_core_facets),
confidence, fallback_reason。
"""

_FILTER_SCALAR_FIELDS = {
    "people_count_min",
    "people_count_max",
    "has_people",
    "has_animals",
    "indoor_outdoor",
    "weather",
    "time_of_day",
}

_METADATA_FILTER_SCALAR_FIELDS = {
    "year",
    "month",
    "date_from",
    "date_to",
    "season",
    "has_gps",
    "camera_make",
    "camera_model",
    "iso_min",
    "iso_max",
    "metadata_only",
}


def _extract_json_object(raw_text: str) -> dict:
    """Extract first valid JSON object from model text output."""
    text = raw_text.strip()
    if not text:
        raise ValueError("Empty planner output")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start < 0:
        raise ValueError("Planner output does not contain a JSON object")

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start: idx + 1]
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError("Extracted planner JSON is not an object")

    raise ValueError("Unable to extract complete planner JSON object")


def _render_prompt(template: str, *, query: str, project_id: Optional[int]) -> str:
    rendered = template
    rendered = rendered.replace("{{query}}", query)
    rendered = rendered.replace("{{today}}", str(date.today()))
    rendered = rendered.replace("{{project_id}}", str(project_id or ""))
    return rendered


def _sanitize_preview(raw_text: str) -> str:
    compact = re.sub(r"\s+", " ", raw_text).strip()
    return compact[:320]


def _normalize_empty_list_scalars(raw_json: dict) -> dict:
    """Normalize LLM placeholder [] into null for scalar filter fields.

    Some small models emit [] for nullable scalar fields. We normalize these
    placeholders before strict schema validation.
    """
    normalized = dict(raw_json)

    filters = normalized.get("filters")
    if isinstance(filters, dict):
        normalized_filters = dict(filters)
        for key in _FILTER_SCALAR_FIELDS:
            value = normalized_filters.get(key)
            if isinstance(value, list) and len(value) == 0:
                normalized_filters[key] = None
        normalized["filters"] = normalized_filters

    metadata_filters = normalized.get("metadata_filters")
    if isinstance(metadata_filters, dict):
        normalized_metadata_filters = dict(metadata_filters)
        for key in _METADATA_FILTER_SCALAR_FIELDS:
            value = normalized_metadata_filters.get(key)
            if isinstance(value, list) and len(value) == 0:
                normalized_metadata_filters[key] = None
        normalized["metadata_filters"] = normalized_metadata_filters

    return normalized


def resolve_query_plan_llm_first(
    query: str,
    *,
    project_id: Optional[int],
    settings: EffectiveSearchSettings,
    understander: Callable,
    include_raw_output: bool = False,
) -> SearchQueryPlan:
    """Resolve SearchQueryPlan through LLM first, then fallback to rules."""
    planner_debug: dict = {
        "provider": settings.query_planner_provider,
        "model": settings.query_planner_model_name,
        "planner_version": settings.query_planner_planner_version,
        "used_fallback": False,
        "fallback_reason": "",
        "latency_ms": 0,
        "raw_output_preview": "",
        "parsed": False,
        "confidence": 0.0,
        "enabled": settings.query_planner_enabled,
    }

    if not settings.query_planner_enabled:
        planner_debug["used_fallback"] = True
        planner_debug["fallback_reason"] = "query_planner_disabled"
        return build_fallback_plan(
            query=query,
            project_id=project_id,
            understander=understander,
            concept_taxonomy=settings.concept_taxonomy,
            rule_base_pack_id=settings.query_understanding_base_pack,
            rule_extension_pack_ids=settings.query_understanding_extension_packs,
            planner_debug=planner_debug,
        )

    fallback_plan = build_fallback_plan(
        query=query,
        project_id=project_id,
        understander=understander,
        concept_taxonomy=settings.concept_taxonomy,
        rule_base_pack_id=settings.query_understanding_base_pack,
        rule_extension_pack_ids=settings.query_understanding_extension_packs,
        planner_debug=planner_debug,
    )

    if not settings.query_planner_endpoint_url.strip() or not settings.query_planner_model_name.strip():
        planner_debug["used_fallback"] = True
        planner_debug["fallback_reason"] = "query_planner_missing_endpoint_or_model"
        fallback_plan.planner_debug = dict(planner_debug)
        return fallback_plan

    system_prompt = settings.query_planner_system_prompt.strip() or _DEFAULT_SYSTEM_PROMPT
    user_prompt_template = settings.query_planner_prompt_template.strip() or _DEFAULT_USER_PROMPT_TEMPLATE
    user_prompt = _render_prompt(
        user_prompt_template,
        query=query,
        project_id=project_id,
    )

    started = time.monotonic()
    try:
        raw_text = call_chat_completion(
            endpoint_url=settings.query_planner_endpoint_url,
            api_key=settings.query_planner_api_key or global_settings.openai_api_key,
            model_name=settings.query_planner_model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.query_planner_temperature,
            top_p=settings.query_planner_top_p,
            max_tokens=settings.query_planner_max_tokens,
            timeout_seconds=settings.query_planner_timeout_seconds,
        )
        planner_debug["latency_ms"] = int((time.monotonic() - started) * 1000)
        planner_debug["raw_output_preview"] = _sanitize_preview(raw_text)
        if include_raw_output:
            planner_debug["raw_output"] = raw_text

        raw_json = _extract_json_object(raw_text)
        raw_json = _normalize_empty_list_scalars(raw_json)
        parsed = LLMQueryPlannerOutput.model_validate(raw_json)

        planner_debug["parsed"] = True
        planner_debug["confidence"] = float(parsed.confidence or 0.0)
        planner_debug["used_fallback"] = False
        planner_debug["fallback_reason"] = ""

        return planner_output_to_query_plan(
            query=query,
            output=parsed,
            planner_debug=planner_debug,
            fallback_plan=fallback_plan,
        )
    except (QueryPlannerClientError, ValueError, json.JSONDecodeError) as exc:
        planner_debug["latency_ms"] = int((time.monotonic() - started) * 1000)
        planner_debug["used_fallback"] = True
        planner_debug["fallback_reason"] = f"planner_error:{exc.__class__.__name__}"
        planner_debug["error"] = str(exc)
        fallback_plan.planner_debug = dict(planner_debug)
        logger.warning(
            "LLM query planner failed; fallback to rule planner. project_id=%s error=%s",
            project_id,
            exc,
        )
        return fallback_plan
