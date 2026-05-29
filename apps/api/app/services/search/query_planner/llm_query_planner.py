"""LLM-first query planner with deterministic rule fallback."""
from __future__ import annotations

import copy
import json
import logging
import re
import threading
import time
from collections import OrderedDict
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

_QUERY_PLAN_CACHE_LOCK = threading.Lock()
_QUERY_PLAN_CACHE_MAX_SIZE = 512
_QUERY_PLAN_CACHE_TTL_SECONDS = 600
_QUERY_PLAN_CACHE: "OrderedDict[tuple, tuple[float, SearchQueryPlan]]" = OrderedDict()

# Intent set that is safe to use in rule fast path when there is NO metadata
# (e.g. a short, clear single-domain query like "动物", "合照", "夜景")
_FAST_PATH_SINGLE_DOMAIN_INTENTS = {
    "animal_search",
    "group_photo_search",
    "people_search",
    "ocr_text_search",
    "food_search",
    "weather_search",
    "activity_search",
    "location_search",
}

_DEFAULT_SYSTEM_PROMPT = (
    "你是 ai-photo-lib 的照片搜索 Query Planner。"
    "你的任务是把用户自然语言查询转换成严格 JSON 搜索计划。"
    "不能输出解释、Markdown、代码块或 JSON 之外的任何文本。"
)

_DEFAULT_USER_PROMPT_TEMPLATE = """请为以下照片搜索请求生成 JSON 搜索计划。

用户 query: {{query}}
当前日期: {{today}}
项目 ID: {{project_id}}

分析步骤（必须按顺序执行）：
1. 识别 metadata 条件：时间（年/月/季节/日期范围）、地点（place_terms）、相机型号、GPS。
2. 去掉 metadata 词后，剩余的核心视觉语义是什么（semantic residual）。
3. 若 semantic residual 为空 → metadata_filters.metadata_only=true；否则 false。
4. 将 semantic residual 展开为 facets（activity/scene/object/people/weather/time/location）和 terms。
5. semantic_query_text：只描述视觉内容，不重复 metadata 词，供向量检索使用。
6. 复合查询（既有 metadata 又有 semantic residual）时，query_constraints.allow_weak_only_match=true。

terms 规则：
- exact：核心视觉语义锚点词，不含 metadata 词，不含整句原文。示例：["滑雪","张家口"]
- expanded：exact 的近义词和场景词。示例：["滑雪场","雪地","冬季运动"]
- support：上下文辅助词，不单独召回。示例：["户外","冬天","旅行"]
- negative：明确排除词。

示例 1 — "去年张家口滑雪"（复合查询）：
metadata_filters: {year:2025, date_from:"2025-01-01", date_to:"2026-01-01", place_terms:["张家口"], metadata_only:false, matched_metadata_terms:["去年","张家口"]}
semantic residual: "滑雪"
terms.exact: ["滑雪","张家口"]
terms.expanded: ["滑雪场","雪地","冬季运动"]
semantic_query_text: "滑雪 雪地 滑雪场 冬季运动 户外运动 张家口冬季"
query_constraints.allow_weak_only_match: true

示例 2 — "去年"（纯 metadata 查询）：
metadata_filters: {year:2025, metadata_only:true, matched_metadata_terms:["去年"]}
terms.exact: []
semantic_query_text: ""
query_constraints.allow_weak_only_match: false

必须输出合法 JSON，包含字段：
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


def _build_cache_key(
    *,
    query: str,
    project_id: Optional[int],
    settings: EffectiveSearchSettings,
) -> tuple:
    return (
        int(project_id or 0),
        query.strip().lower(),
        settings.query_planner_provider,
        settings.query_planner_endpoint_url.strip(),
        settings.query_planner_model_name.strip(),
        settings.query_planner_planner_version,
        settings.query_understanding_base_pack,
        tuple(settings.query_understanding_extension_packs),
    )


def _cache_get(cache_key: tuple) -> Optional[SearchQueryPlan]:
    now = time.monotonic()
    with _QUERY_PLAN_CACHE_LOCK:
        hit = _QUERY_PLAN_CACHE.get(cache_key)
        if not hit:
            return None
        created_at, cached_plan = hit
        if now - created_at > _QUERY_PLAN_CACHE_TTL_SECONDS:
            _QUERY_PLAN_CACHE.pop(cache_key, None)
            return None
        _QUERY_PLAN_CACHE.move_to_end(cache_key)
        return copy.deepcopy(cached_plan)


def _cache_put(cache_key: tuple, query_plan: SearchQueryPlan) -> None:
    with _QUERY_PLAN_CACHE_LOCK:
        _QUERY_PLAN_CACHE[cache_key] = (time.monotonic(), copy.deepcopy(query_plan))
        _QUERY_PLAN_CACHE.move_to_end(cache_key)
        while len(_QUERY_PLAN_CACHE) > _QUERY_PLAN_CACHE_MAX_SIZE:
            _QUERY_PLAN_CACHE.popitem(last=False)


def _has_metadata_filters(metadata_filters: dict) -> bool:
    """Return True if any structured metadata filter was populated."""
    return any(
        metadata_filters.get(key) not in (None, "", [], {})
        for key in (
            "year",
            "month",
            "date_from",
            "date_to",
            "camera_make",
            "camera_model",
            "iso_min",
            "iso_max",
        )
    ) or bool(metadata_filters.get("place_terms"))


def _should_use_rule_fast_path(query: str, fallback_plan: SearchQueryPlan) -> tuple[bool, str]:
    """Determine whether the rule planner result can be used without calling the LLM.

    Rule:
    * Empty query                                   → fast path (trivial)
    * metadata_only == True                         → fast path (pure EXIF filter)
    * has metadata AND NOT metadata_only            → LLM required (compound query)
    * short + no metadata + clear single intent     → fast path
    * Everything else                               → LLM required
    """
    normalized_query = query.strip().lower()
    if not normalized_query:
        return True, "empty_query"

    metadata_filters = fallback_plan.metadata_filters or {}

    # Pure metadata query (no semantic residual detected by rule engine)
    if metadata_filters.get("metadata_only") is True:
        return True, "metadata_only"

    # Compound query: has structured metadata but also has semantic residual
    # These MUST go to LLM so the planner can output residual semantic tasks.
    if _has_metadata_filters(metadata_filters):
        return False, ""

    # No metadata at all — allow fast path for short, unambiguous single-domain queries
    exact_terms = fallback_plan.exact_terms or []
    is_short = len(normalized_query) <= 10 and len(exact_terms) <= 2
    has_clear_intent = (
        fallback_plan.intent is not None
        and fallback_plan.intent not in ("semantic_photo_search",)
        and fallback_plan.intent in _FAST_PATH_SINGLE_DOMAIN_INTENTS
    )
    if is_short and has_clear_intent:
        return True, f"short_clear_intent:{fallback_plan.intent}"

    # Very short query that matched dictionary keys
    if fallback_plan.matched_keys and len(normalized_query) <= 8:
        return True, "short_matched_dictionary"

    return False, ""


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
        planner_debug["planner_route"] = "rule_only"
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

    cache_key: Optional[tuple] = None
    if not include_raw_output:
        use_rule_fast_path, fast_path_reason = _should_use_rule_fast_path(query, fallback_plan)
        if use_rule_fast_path:
            planner_debug["used_fallback"] = True
            planner_debug["fallback_reason"] = f"rule_fast_path:{fast_path_reason}"
            planner_debug["fast_path"] = True
            planner_debug["planner_route"] = "rule_fast_path"
            fallback_plan.planner_debug = dict(planner_debug)
            return fallback_plan

        cache_key = _build_cache_key(query=query, project_id=project_id, settings=settings)
        cached_plan = _cache_get(cache_key)
        if cached_plan is not None:
            cached_debug = dict(cached_plan.planner_debug or {})
            cached_debug.update(
                {
                    "enabled": settings.query_planner_enabled,
                    "provider": settings.query_planner_provider,
                    "model": settings.query_planner_model_name,
                    "planner_version": settings.query_planner_planner_version,
                    "cache_hit": True,
                    "used_fallback": False,
                    "fallback_reason": "",
                }
            )
            cached_plan.planner_debug = cached_debug
            return cached_plan

    if not settings.query_planner_endpoint_url.strip() or not settings.query_planner_model_name.strip():
        planner_debug["used_fallback"] = True
        planner_debug["fallback_reason"] = "query_planner_missing_endpoint_or_model"
        planner_debug["planner_route"] = "rule_only"
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
        planner_timeout_seconds = max(1, int(settings.query_planner_timeout_seconds))

        raw_text = call_chat_completion(
            endpoint_url=settings.query_planner_endpoint_url,
            api_key=settings.query_planner_api_key or global_settings.openai_api_key,
            model_name=settings.query_planner_model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.query_planner_temperature,
            top_p=settings.query_planner_top_p,
            max_tokens=settings.query_planner_max_tokens,
            timeout_seconds=planner_timeout_seconds,
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
        planner_debug["planner_route"] = "llm"

        query_plan = planner_output_to_query_plan(
            query=query,
            output=parsed,
            planner_debug=planner_debug,
            fallback_plan=fallback_plan,
        )
        if cache_key is not None:
            _cache_put(cache_key, query_plan)
        return query_plan
    except (QueryPlannerClientError, ValueError, json.JSONDecodeError) as exc:
        planner_debug["latency_ms"] = int((time.monotonic() - started) * 1000)
        planner_debug["used_fallback"] = True
        is_timeout = isinstance(exc, QueryPlannerClientError) and "timed out" in str(exc).lower()
        planner_debug["fallback_reason"] = (
            "planner_timeout_fallback"
            if is_timeout
            else f"planner_error:{exc.__class__.__name__}"
        )
        planner_debug["planner_route"] = "fallback_after_error"
        planner_debug["error"] = str(exc)
        fallback_plan.planner_debug = dict(planner_debug)
        logger.warning(
            "LLM query planner failed; fallback to rule planner. project_id=%s error=%s",
            project_id,
            exc,
        )
        return fallback_plan
