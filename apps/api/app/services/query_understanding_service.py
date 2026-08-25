"""Rule-based query understanding service.

This rule pack is a fallback and deterministic baseline for the LLM query
planner. Keep new compound planning behavior in the planner prompt/evaluation
set instead of expanding lifestyle_default.json as the primary brain.

Five-tier term model
--------------------
must_terms (exact_terms)
    Words taken directly from the user's query.  Strongest evidence.

strong_terms (expanded_terms)
    Direct synonyms / near-equivalent terms (score × 0.7).
    Can independently trigger keyword recall.

support_terms
    Context clues that need combining with other evidence (score × 0.5).
    NOT sole recall triggers — only boost already-recalled photos.

weak_terms (broad_terms)
    Generic category terms (score × 0.3).
    Boost-only, never sole recall triggers.

negative_terms
    Conflicting / contradictory terms — penalise matching photos.

``intent_facets``  maps facet names to associated terms from the query.
``query_constraints``  per-query evidence requirements for display.

Backward-compatible aliases:
    exact_terms    = must_terms
    expanded_terms = strong_terms  (recall_terms = exact + expanded)
    broad_terms    = weak_terms
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Literal, Optional

from .query_understanding_rule_packs import (
    DEFAULT_BASE_PACK_ID,
    QueryUnderstandingRuleSet,
    build_rule_set,
    normalise_extension_pack_ids,
)

# ── Chinese query noise cleaning ──────────────────────────────────────────────
#
# Strip suffixes and prefixes that carry no photo-search semantics.
# Applied before tokenisation so they don't become spurious exact_terms.

_NOISE_SUFFIXES = re.compile(
    r"(的照片|的图片|的相片|照片|图片|相片|的图|图)$"
)
_NOISE_PREFIXES = re.compile(
    r"^(搜索|找一下|帮我找|请找|查找|给我看)"
)

_DYNAMIC_FILTER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"人数\s*(?:大于|超过)\s*(\d+)|超过\s*(\d+)\s*人"), "gt"),
    (
        re.compile(
            r"人数\s*(?:不少于|至少|大于等于)\s*(\d+)"
            r"|(?:至少|不少于)\s*(\d+)\s*人(?:的)?"
            r"|(\d+)\s*人以上(?:的)?"
        ),
        "gte",
    ),
    (re.compile(r"人数\s*(?:小于|少于)\s*(\d+)|少于\s*(\d+)\s*人"), "lt"),
    (re.compile(r"人数\s*(?:不超过|至多|小于等于)\s*(\d+)|(\d+)\s*人以下"), "lte"),
    (re.compile(r"人数\s*(?:等于|为|是)\s*(\d+)|(?:正好|恰好)\s*(\d+)\s*人"), "eq"),
)

_SORT_PATTERNS: tuple[tuple[re.Pattern[str], dict[str, str]], ...] = (
    (
        re.compile(
            r"(?:按)?(?:拍摄)?时间(?:倒序|降序)"
            r"|(?:最新|最近)(?:拍摄)?(?:的)?(?:照片|图片|相片)?(?:优先|在前)?"
        ),
        {"field": "taken_at", "order": "desc"},
    ),
    (
        re.compile(
            r"(?:按)?(?:拍摄)?时间(?:正序|升序)"
            r"|(?:最早|最旧)(?:拍摄)?(?:的)?(?:照片|图片|相片)?(?:优先|在前)?"
        ),
        {"field": "taken_at", "order": "asc"},
    ),
)


def _parse_dynamic_query_controls(query: str) -> tuple[str, list[dict], list[dict]]:
    """Extract deterministic controls while preserving the semantic residual."""
    residual = query
    filter_clauses: list[dict] = []
    sort_specs: list[dict] = []

    for pattern, operator in _DYNAMIC_FILTER_PATTERNS:
        match = pattern.search(residual)
        if match is None:
            continue
        raw_value = next((value for value in match.groups() if value is not None), None)
        if raw_value is not None:
            filter_clauses.append(
                {"field": "people_count", "operator": operator, "value": int(raw_value)}
            )
        residual = pattern.sub(" ", residual)
        break

    for pattern, sort_spec in _SORT_PATTERNS:
        if pattern.search(residual) is None:
            continue
        sort_specs.append(dict(sort_spec))
        residual = pattern.sub(" ", residual)
        break

    residual = re.sub(r"[,，;；]+", " ", residual)
    residual = re.sub(r"\s+", " ", residual).strip()
    return residual, filter_clauses, sort_specs


def _clean_chinese_query(query: str) -> str:
    """Strip common Chinese noise words that add no search value."""
    q = query.strip()
    # Repeatedly strip suffix noise (e.g. "猫的照片" → "猫", "猫的图片" → "猫")
    prev = None
    while prev != q:
        prev = q
        q = _NOISE_SUFFIXES.sub("", q).strip()
    # Strip prefix noise
    q = _NOISE_PREFIXES.sub("", q).strip()
    # Fall back to original if cleaning made the query empty
    return q if q else query.strip()


# ── Metadata (EXIF / Photo field) filter parser ───────────────────────────────

_CHINESE_MONTH_TO_NUM: dict[str, int] = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
}
# Matches: 1-12月 / 1-12月份 / 一月 … 十二月
_MONTH_RE = re.compile(r"(十[一二]|[一二三四五六七八九十]|1[0-2]|[1-9])月(?:份)?")
# Matches 2-/4-digit year followed by 年: 2024年 1999年
_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})年")
# Noise to strip when detecting metadata-only query
_META_NOISE_RE = re.compile(
    r"的照片|的相片|的图片|的图|照片|相片|图片|拍的|拍摄|摄影|帮我找|搜索|找|查|"
    r"地址|地点|位置|拍摄地|拍摄地点|拍摄位置|位于|在|于|是|为|的|了|里|中"
)
_PLACE_PARSE_NOISE_RE = re.compile(
    r"的照片|的相片|的图片|的图|照片|相片|图片|拍的|拍摄|摄影|帮我找|搜索|找|查"
)
_PLACE_SPLIT_RE = re.compile(r"[\s,/，、的]+")
_GENERIC_NON_PLACE_TERMS: frozenset[str] = frozenset({
    "夜景", "夜晚", "室内", "室外", "风景", "美食", "食物", "人物", "建筑", "街景",
    "动物", "宠物", "野生动物", "小动物", "猫", "狗", "鸟", "马", "鹿", "兔", "兔子", "鱼",
    "下雨天", "晴天", "雪天", "海边", "日落", "日出", "晚霞", "自拍", "滑雪",
})
_CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_PLACE_PREFIX_NOISE: tuple[str, ...] = (
    "拍摄地点是",
    "拍摄地点在",
    "拍摄位置是",
    "拍摄位置在",
    "拍摄地是",
    "拍摄地在",
    "地点是",
    "地点在",
    "位置是",
    "位置在",
    "地址是",
    "地址在",
    "拍摄地点",
    "拍摄位置",
    "拍摄地",
    "地址",
    "地点",
    "位置",
    "位于",
    "在",
    "于",
    "是",
    "为",
)
_LOCATION_QUERY_CUE_RE = re.compile(
    r"地址|地点|位置|拍摄地|拍摄地点|拍摄位置|位于|在.*(照片|图片|相片|拍)|于.*(照片|图片|相片|拍)|拍的"
)

# Strong semantic intents should never be treated as metadata-only requests,
# even if metadata parser matched some tokens.
_METADATA_ONLY_BLOCKED_INTENTS: frozenset[str] = frozenset({
    "animal_search",
    "people_search",
    "group_photo_search",
    "food_search",
    "weather_search",
    "activity_search",
})

_ANIMAL_CATEGORY_TERMS: frozenset[str] = frozenset({
    "动物", "宠物", "野生动物", "动物园", "小动物", "animal",
})


def _is_cjk_char(ch: str) -> bool:
    return bool(ch) and bool(_CJK_CHAR_RE.match(ch))


def _term_in_query(term: str, query_lower: str) -> bool:
    """Return True when *term* should be treated as matched in *query_lower*.

    Single-character CJK terms require at least one-side boundary to avoid
    false positives like "家" in "张家口".
    """
    token = str(term or "").strip().lower()
    if not token:
        return False
    if token not in query_lower:
        return False
    if len(token) != 1 or (not _is_cjk_char(token)):
        return True

    start = 0
    q_len = len(query_lower)
    while True:
        idx = query_lower.find(token, start)
        if idx < 0:
            return False
        prev_ch = query_lower[idx - 1] if idx > 0 else ""
        next_idx = idx + 1
        next_ch = query_lower[next_idx] if next_idx < q_len else ""
        prev_is_cjk = _is_cjk_char(prev_ch)
        next_is_cjk = _is_cjk_char(next_ch)
        if (not prev_is_cjk) or (not next_is_cjk):
            return True
        start = idx + 1


def _strip_non_place_affixes(term: str) -> str:
    cleaned = str(term or "").strip()
    if not cleaned:
        return ""

    for prefix in _PLACE_PREFIX_NOISE:
        if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
            cleaned = cleaned[len(prefix):].strip()

    non_place_terms = sorted(_GENERIC_NON_PLACE_TERMS, key=len, reverse=True)
    changed = True
    while changed and cleaned:
        changed = False
        for prefix in _PLACE_PREFIX_NOISE:
            if cleaned.startswith(prefix) and len(cleaned) > len(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
                break
        if changed:
            continue
        for bad in non_place_terms:
            if len(cleaned) <= len(bad):
                continue
            if cleaned.startswith(bad):
                cleaned = cleaned[len(bad):].strip()
                changed = True
                break
            if cleaned.endswith(bad):
                cleaned = cleaned[: -len(bad)].strip()
                changed = True
                break
    return cleaned


def _has_location_query_cue(query: str) -> bool:
    return bool(_LOCATION_QUERY_CUE_RE.search(str(query or "")))

def _normalise_concept_taxonomy(
    raw: Optional[list[dict]],
    default_taxonomy: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not raw:
        return list(default_taxonomy)

    normalized: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        concept = str(item.get("concept") or "").strip()
        if not concept:
            continue
        normalized.append(
            {
                "concept": concept,
                "children": [
                    str(v).strip()
                    for v in (item.get("children") or [])
                    if str(v).strip()
                ],
                "child_negative_contexts": [
                    str(v).strip()
                    for v in (item.get("child_negative_contexts") or [])
                    if str(v).strip()
                ],
                "aliases": [
                    str(v).strip()
                    for v in (item.get("aliases") or [])
                    if str(v).strip()
                ],
                "positive_fields": [
                    str(v).strip()
                    for v in (item.get("positive_fields") or [])
                    if str(v).strip()
                ],
                "negative_terms": [
                    str(v).strip()
                    for v in (item.get("negative_terms") or [])
                    if str(v).strip()
                ],
                "recall_policy": str(item.get("recall_policy") or "").strip(),
                "evidence_policy": str(item.get("evidence_policy") or "").strip(),
            }
        )
    return normalized or list(default_taxonomy)


def _child_matches_with_context(
    child: str,
    query_lower: str,
    child_negative_contexts: list[str],
) -> bool:
    """Return True if *child* appears in *query_lower* and is NOT inside a negative-context phrase.

    Prevents single-char animal words (e.g. "鱼") from matching compound activity
    phrases (e.g. "钓鱼") and triggering an animal concept incorrectly.
    """
    if child.lower() not in query_lower:
        return False
    # If any negative-context phrase is present in the query, this child match
    # is embedded in an activity compound word — treat as not matched.
    for neg_ctx in child_negative_contexts:
        if neg_ctx.lower() in query_lower:
            return False
    return True


def _apply_concept_taxonomy(
    *,
    query_lower: str,
    exact_lower: set[str],
    expanded_set: set[str],
    broad_set: set[str],
    matched_keys_set: list[str],
    concept_taxonomy: list[dict[str, object]],
) -> list[str]:
    """Apply concept taxonomy expansion and return matched concept terms."""
    concept_terms: list[str] = []

    for entry in concept_taxonomy:
        concept = str(entry.get("concept") or "").strip()
        if not concept:
            continue
        aliases = [str(v).strip() for v in (entry.get("aliases") or []) if str(v).strip()]
        children = [str(v).strip() for v in (entry.get("children") or []) if str(v).strip()]
        child_negative_contexts = [
            str(v).strip() for v in (entry.get("child_negative_contexts") or []) if str(v).strip()
        ]
        recall_policy = str(entry.get("recall_policy") or "expand_children").strip()

        concept_matched = concept.lower() in query_lower
        alias_matched = any(alias.lower() in query_lower for alias in aliases)
        child_matched = any(
            _child_matches_with_context(child, query_lower, child_negative_contexts)
            for child in children
        )
        if not (concept_matched or alias_matched or child_matched):
            continue

        if concept not in concept_terms:
            concept_terms.append(concept)
        if concept not in matched_keys_set:
            matched_keys_set.append(concept)

        if recall_policy == "expand_children" and (concept_matched or alias_matched):
            for child in children:
                if child.lower() not in exact_lower:
                    expanded_set.add(child)
        if child_matched and concept.lower() not in exact_lower:
            broad_set.add(concept)

    return concept_terms


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        text = term.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(text)
    return deduped


def _build_semantic_query_text(
    *,
    original_query: str,
    intent: str,
    exact_terms: list[str],
    expanded_terms: list[str],
    broad_terms: list[str],
) -> str:
    all_terms = _dedupe_terms(exact_terms + expanded_terms + broad_terms)
    if not all_terms:
        return original_query

    if intent == "animal_search":
        entity_terms = [
            term for term in _dedupe_terms(exact_terms + expanded_terms)
            if term not in _ANIMAL_CATEGORY_TERMS and term != "野外"
        ]
        broad_semantics = [
            term for term in _dedupe_terms(broad_terms)
            if term not in {"动物园"}
        ]

        parts = ["查找包含动物主体的照片"]
        if entity_terms:
            parts.append(f"，包括{'、'.join(entity_terms)}")
        if broad_semantics:
            parts.append(f"，以及{'、'.join(broad_semantics)}")
        parts.append("。重点匹配 object_tags、search_keywords、caption 中出现动物实体的照片。")
        return "".join(parts)

    return (
        f"查找与以下内容相关的照片：{'、'.join(all_terms)}。"
        "重点匹配 caption、tags、search_keywords 和 OCR 文本。"
    )


def _parse_metadata_filters(original_query: str) -> dict:
    """Parse EXIF / Photo table metadata filters from a raw user query.

    Returns a dict with keys:
        date_from, date_to   — ISO date strings (str | None)
        year                 — int | None
        month                — int 1-12 | None
        months               — list[int] for season ranges
        season               — str | None ('spring'/'summer'/'autumn'/'winter')
        has_gps              — bool | None
        camera_make          — str | None  (used for ILIKE)
        camera_model         — str | None  (used for ILIKE, combined with camera_make)
        iso_min              — int | None
        iso_max              — int | None
        place_terms          — list[str]
        metadata_only        — bool  (True if no semantic content remains after filters)
        matched_metadata_terms — list[str]  (human-readable matched terms)
    """
    q = original_query
    today = date.today()
    current_year = today.year

    result: dict = {
        "date_from": None,
        "date_to": None,
        "year": None,
        "month": None,
        "months": [],
        "season": None,
        "has_gps": None,
        "camera_make": None,
        "camera_model": None,
        "iso_min": None,
        "iso_max": None,
        "place_terms": [],
        "metadata_only": False,
        "matched_metadata_terms": [],
    }
    matched: list[str] = []
    remaining = q  # we strip matched terms from here for metadata_only detection

    def _strip(s: str, pattern: str) -> str:
        return s.replace(pattern, "")

    # ── Relative year: 今年 / 去年 ──────────────────────────────────────────
    rel_year_m = re.search(r"今年|去年", q)
    year: int | None = None
    if rel_year_m:
        year = current_year if rel_year_m.group() == "今年" else current_year - 1
        matched.append(rel_year_m.group())
        remaining = _strip(remaining, rel_year_m.group())

    # ── Absolute year: 2024年 ──────────────────────────────────────────────
    abs_year_m = _YEAR_RE.search(q)
    if abs_year_m:
        year = int(abs_year_m.group(1))  # absolute overrides relative
        matched.append(abs_year_m.group())
        remaining = _strip(remaining, abs_year_m.group())

    # ── Month: 12月 / 十二月 / 12月份 ────────────────────────────────────
    month_m = _MONTH_RE.search(q)
    month: int | None = None
    if month_m:
        raw = month_m.group(1)
        month = int(raw) if raw.isdigit() else _CHINESE_MONTH_TO_NUM.get(raw)
        if month and 1 <= month <= 12:
            matched.append(month_m.group())
            remaining = _strip(remaining, month_m.group())
        else:
            month = None

    # ── Build date_from / date_to ─────────────────────────────────────────
    if year is not None and month is not None:
        result["year"] = year
        result["month"] = month
        next_m_year = year + 1 if month == 12 else year
        next_m = 1 if month == 12 else month + 1
        result["date_from"] = f"{year}-{month:02d}-01"
        result["date_to"] = f"{next_m_year}-{next_m:02d}-01"
    elif year is not None:
        result["year"] = year
        result["date_from"] = f"{year}-01-01"
        result["date_to"] = f"{year + 1}-01-01"
    elif month is not None:
        result["month"] = month

    # ── Season ────────────────────────────────────────────────────────────
    _SEASON_PATTERNS = [
        (r"春天|春季|春分", "spring", [3, 4, 5]),
        (r"夏天|夏季|夏日", "summer", [6, 7, 8]),
        (r"秋天|秋季|秋分", "autumn", [9, 10, 11]),
        (r"冬天|冬季|冬日", "winter", [12, 1, 2]),
    ]
    for sp, en_name, months_list in _SEASON_PATTERNS:
        sm = re.search(sp, q)
        if sm:
            result["season"] = en_name
            result["months"] = months_list
            matched.append(sm.group())
            remaining = _strip(remaining, sm.group())
            break

    # ── GPS ───────────────────────────────────────────────────────────────
    if re.search(r"没有GPS|无GPS|无定位|无位置", q):
        result["has_gps"] = False
        matched.append("无GPS")
        remaining = re.sub(r"没有GPS|无GPS|无定位|无位置", "", remaining)
    elif re.search(r"有GPS|有定位|有位置", q):
        result["has_gps"] = True
        matched.append("有GPS")
        remaining = re.sub(r"有GPS|有定位|有位置", "", remaining)

    # ── Camera make / model ───────────────────────────────────────────────
    _CAMERA_PATTERNS = [
        (r"(?<![A-Za-z0-9])iphone(?![A-Za-z0-9])", "Apple", "iPhone"),
        (r"(?<![A-Za-z0-9])apple(?![A-Za-z0-9])|苹果手机", "Apple", None),
        (r"(?<![A-Za-z0-9])sony(?![A-Za-z0-9])|索尼", "Sony", None),
        (r"(?<![A-Za-z0-9])canon(?![A-Za-z0-9])|佳能", "Canon", None),
        (r"(?<![A-Za-z0-9])nikon(?![A-Za-z0-9])|尼康", "Nikon", None),
        (r"(?<![A-Za-z0-9])dji(?![A-Za-z0-9])|大疆", "DJI", None),
        (r"(?<![A-Za-z0-9])huawei(?![A-Za-z0-9])|华为", "Huawei", None),
        (r"(?<![A-Za-z0-9])samsung(?![A-Za-z0-9])|三星", "Samsung", None),
        (r"(?<![A-Za-z0-9])fuji(?:film)?(?![A-Za-z0-9])|富士", "FUJIFILM", None),
        (r"(?<![A-Za-z0-9])panasonic(?![A-Za-z0-9])|松下", "Panasonic", None),
        (r"(?<![A-Za-z0-9])olympus(?![A-Za-z0-9])|奥林巴斯", "Olympus", None),
        (r"(?<![A-Za-z0-9])leica(?![A-Za-z0-9])|徕卡", "Leica", None),
    ]
    for cp, make, model_hint in _CAMERA_PATTERNS:
        cm = re.search(cp, q, re.IGNORECASE)
        if cm:
            result["camera_make"] = make
            if model_hint:
                result["camera_model"] = model_hint
            matched.append(cm.group())
            remaining = re.sub(cp, "", remaining, flags=re.IGNORECASE)
            break

    # ── ISO ───────────────────────────────────────────────────────────────
    iso_exact_m = re.search(r"\biso\s*(\d+)\b", q, re.IGNORECASE)
    if iso_exact_m:
        iso_val = int(iso_exact_m.group(1))
        result["iso_min"] = iso_val
        result["iso_max"] = iso_val
        matched.append(f"ISO {iso_val}")
        remaining = re.sub(r"\biso\s*\d+\b", "", remaining, flags=re.IGNORECASE)
    elif re.search(r"高iso|高感光|高感", q, re.IGNORECASE):
        result["iso_min"] = 800
        matched.append("高ISO")
        remaining = re.sub(r"高iso|高感光|高感", "", remaining, flags=re.IGNORECASE)

    # ── Structured place terms ─────────────────────────────────────────────
    should_extract_place = bool(
        _has_location_query_cue(q)
        or year is not None
        or month is not None
    )
    cleaned_remaining = _PLACE_PARSE_NOISE_RE.sub("", remaining).strip()
    place_terms: list[str] = []
    if should_extract_place and cleaned_remaining:
        for raw_term in _PLACE_SPLIT_RE.split(cleaned_remaining):
            term = _strip_non_place_affixes(raw_term.strip())
            if not term or term in _GENERIC_NON_PLACE_TERMS:
                continue
            if term not in place_terms:
                place_terms.append(term)
    if not place_terms:
        composite_match = re.match(r"^([\u4e00-\u9fff]{2,8})的([\u4e00-\u9fffA-Za-z0-9]{1,12})$", q.strip())
        if composite_match:
            maybe_place = composite_match.group(1)
            semantic_tail = composite_match.group(2)
            if semantic_tail in _GENERIC_NON_PLACE_TERMS:
                place_terms.append(maybe_place)
    if place_terms:
        result["place_terms"] = place_terms
        matched.extend(place_terms)
        for term in place_terms:
            remaining = _strip(remaining, term)

    result["matched_metadata_terms"] = matched

    # ── metadata_only detection ────────────────────────────────────────────
    # If any filter was matched, check whether anything meaningful remains
    has_any = bool(
        result["year"] or result["month"] or result["months"]
        or result["date_from"]
        or (result["has_gps"] is not None)
        or result["camera_make"] or result["camera_model"]
        or (result["iso_min"] is not None) or (result["iso_max"] is not None)
        or result["place_terms"]
    )
    if has_any:
        cleaned = _META_NOISE_RE.sub("", remaining).strip()
        cleaned = re.sub(r"\s+", "", cleaned)
        result["metadata_only"] = len(cleaned) == 0

    return result


@dataclass(frozen=True)
class _RuleRuntime:
    outdoor_terms_tiered: Dict[str, Any]
    weather_terms_tiered: Dict[str, Any]
    animal_terms_tiered: Dict[str, Any]
    people_terms_tiered: Dict[str, Any]
    food_terms_tiered: Dict[str, Any]
    travel_terms_tiered: Dict[str, Any]
    indoor_terms_tiered: Dict[str, Any]
    outdoor_keys: set[str]
    weather_keys: set[str]
    animal_keys: set[str]
    people_keys: set[str]
    food_keys: set[str]
    travel_keys: set[str]
    indoor_keys: set[str]
    activity_phrase_overrides: frozenset[str]
    all_tiered_dicts_with_facets: list[tuple[str, Dict[str, Any]]]


_GROUP_PHOTO_KEYS: set[str] = {
    "合照",
    "合影",
    "集体照",
    "多人",
    "多人合照",
    "多人合影",
    "group photo",
    "全家福",
}


def _build_rule_runtime(rule_set: QueryUnderstandingRuleSet) -> _RuleRuntime:
    tiered_terms = rule_set.tiered_terms
    outdoor_terms_tiered = dict(tiered_terms.get("outdoor") or {})
    weather_terms_tiered = dict(tiered_terms.get("weather") or {})
    animal_terms_tiered = dict(tiered_terms.get("animal") or {})
    people_terms_tiered = dict(tiered_terms.get("people") or {})
    food_terms_tiered = dict(tiered_terms.get("food") or {})
    travel_terms_tiered = dict(tiered_terms.get("travel") or {})
    indoor_terms_tiered = dict(tiered_terms.get("indoor") or {})

    return _RuleRuntime(
        outdoor_terms_tiered=outdoor_terms_tiered,
        weather_terms_tiered=weather_terms_tiered,
        animal_terms_tiered=animal_terms_tiered,
        people_terms_tiered=people_terms_tiered,
        food_terms_tiered=food_terms_tiered,
        travel_terms_tiered=travel_terms_tiered,
        indoor_terms_tiered=indoor_terms_tiered,
        outdoor_keys=set(outdoor_terms_tiered.keys()),
        weather_keys=set(weather_terms_tiered.keys()),
        animal_keys=set(animal_terms_tiered.keys()),
        people_keys=set(people_terms_tiered.keys()),
        food_keys=set(food_terms_tiered.keys()),
        travel_keys=set(travel_terms_tiered.keys()),
        indoor_keys=set(indoor_terms_tiered.keys()),
        activity_phrase_overrides=rule_set.activity_phrase_overrides,
        all_tiered_dicts_with_facets=[
            ("activity", outdoor_terms_tiered),
            ("weather", weather_terms_tiered),
            ("object", animal_terms_tiered),
            ("people", people_terms_tiered),
            ("object", food_terms_tiered),
            ("scene", travel_terms_tiered),
            ("scene", indoor_terms_tiered),
        ],
    )


# ── Penalize tags for semantic_tag_boost (per weather sub-type) ──────────────

_PENALIZE_TAGS_RAIN: list[str] = [
    "室内", "台灯", "动物特写", "月亮", "花朵", "沙地", "晴天", "蓝天", "阳光", "干燥",
]
_PENALIZE_TAGS_SNOW: list[str] = [
    "室内", "花朵", "沙地", "晴天", "蓝天", "阳光", "海边", "夏天",
]
_PENALIZE_TAGS_SUNNY: list[str] = [
    "室内", "阴天", "多云", "雨天", "雨伞", "积水",
]

_LIGHT_QUERY_MAX_EXPANDED_TERMS = 3
_LIGHT_NEGATIVE_ALLOWLIST = {
    "室内",
    "户外",
    "夜晚",
    "白天",
    "晴天",
    "雨天",
    "下雨",
    "下雪",
    "雪天",
    "海边",
    "山地",
}

# ── Intent classification ─────────────────────────────────────────────────────

_OCR_PATTERNS = re.compile(
    r"(order|invoice|id|sn|单号|订单|发票|金额|门牌|车牌|编号|号码|序列号)",
    flags=re.IGNORECASE,
)


def _is_ocr_intent(query: str) -> bool:
    if _OCR_PATTERNS.search(query):
        return True
    digit_count = sum(1 for ch in query if ch.isdigit())
    if digit_count >= 4:
        return True
    if digit_count >= 1 and re.search(r"[A-Za-z]\d|\d[A-Za-z]", query):
        ascii_count = sum(1 for ch in query if ch.isascii() and ch.isalnum())
        if ascii_count >= max(6, len(query) // 2):
            return True
    return False


def _classify_intent(query: str, runtime_rules: _RuleRuntime) -> str:
    if _is_ocr_intent(query):
        return "ocr_text_search"
    q_lower = query.lower()

    # ── Activity 优先检查 ──────────────────────────────────────────────────
    # 必须在 animal 之前：防止"钓鱼/骑马/摸鱼"等复合词因包含"鱼/马"单字
    # 而被误判为 animal_search。
    # 先检查显式活动短语保护集（含动物字的复合活动词）
    if any(_term_in_query(phrase, q_lower) for phrase in runtime_rules.activity_phrase_overrides):
        return "activity_search"
    for key in runtime_rules.outdoor_keys:
        if _term_in_query(key, q_lower):
            return "activity_search"
    for key in runtime_rules.animal_keys:
        if _term_in_query(key, q_lower):
            return "animal_search"
    for key in runtime_rules.weather_keys:
        if _term_in_query(key, q_lower):
            return "weather_search"
    if any(_term_in_query(k, q_lower) for k in _GROUP_PHOTO_KEYS):
        return "group_photo_search"
    if any(_term_in_query(k, q_lower) for k in runtime_rules.people_keys):
        return "people_search"
    if any(_term_in_query(k, q_lower) for k in runtime_rules.food_keys):
        return "food_search"
    if any(_term_in_query(k, q_lower) for k in runtime_rules.travel_keys):
        return "location_search"
    return "semantic_photo_search"


def _recommended_profile(intent: str) -> str:
    return {
        "animal_search": "entity_object",
        "ocr_text_search": "ocr_text",
        "activity_search": "activity_scene",
        "location_search": "location_time",
        "metadata_location_search": "location_time",
        "people_search": "people_group",
        "group_photo_search": "people_group",
    }.get(intent, "default_semantic")


# ── Filter inference ──────────────────────────────────────────────────────────

def _infer_filters(query: str, intent: str, runtime_rules: _RuleRuntime) -> dict:
    filters: dict = {
        "people_count_min": None,
        "people_count_max": None,
        "has_animals": None,
        "has_people": None,
        "indoor_outdoor": None,
        "weather": None,
        "time_of_day": None,
    }
    if intent == "animal_search":
        filters["has_animals"] = True
    if intent in ("people_search", "group_photo_search"):
        filters["has_people"] = True
    if intent == "group_photo_search":
        filters["people_count_min"] = 2

    q_lower = query.lower()
    for key in ("下雨", "rain", "雨天"):
        if key in q_lower:
            filters["weather"] = "rain"
            break
    if filters["weather"] is None:
        for key in ("下雪", "snow", "雪天"):
            if key in q_lower:
                filters["weather"] = "snow"
                break

    if any(_term_in_query(k, q_lower) for k in runtime_rules.outdoor_keys):
        filters["indoor_outdoor"] = "outdoor"
    elif any(_term_in_query(k, q_lower) for k in runtime_rules.indoor_keys):
        filters["indoor_outdoor"] = "indoor"

    if any(k in q_lower for k in ("日落", "sunset", "黄昏", "夕阳")):
        filters["time_of_day"] = "sunset"
    elif any(k in q_lower for k in ("日出", "sunrise", "清晨", "朝霞")):
        filters["time_of_day"] = "morning"
    elif any(k in q_lower for k in ("夜景", "夜晚", "夜色")):
        filters["time_of_day"] = "night"

    return filters


# ── SearchQueryPlan ───────────────────────────────────────────────────────────

@dataclass
class SearchQueryPlan:
    """Structured representation of a parsed search query.

    Five-tier term model
    --------------------
    must_terms / exact_terms
        Words from the user's original query.  Strongest evidence (× 1.0).

    strong_terms / expanded_terms
        Direct synonyms / near-equivalent terms (× 0.7).
        Can independently trigger keyword recall.

    support_terms
        Context clues that need combining with other evidence (× 0.5).
        NOT sole recall triggers — only boost already-recalled photos.

    weak_terms / broad_terms
        Generic category terms (× 0.3).  Boost-only, no recall.

    negative_terms
        Conflicting/contradictory terms.  Photos matching these are penalised.

    intent_facets
        dict[facet_name, list[terms]] capturing what kind of evidence the
        query requires (e.g. {"time": ["夜晚"], "lighting": ["暗光"]}).

    query_constraints
        Default display/evidence requirements for this query.

    Backward-compatible aliases:
        exact_terms    = must_terms
        expanded_terms = strong_terms
        broad_terms    = weak_terms
    """

    original_query: str
    normalized_query: str
    semantic_query_text: str = ""
    # ── backward-compatible fields (kept as primary storage) ─────────────────
    exact_terms: list[str] = field(default_factory=list)     # == must_terms
    expanded_terms: list[str] = field(default_factory=list)  # == strong_terms
    broad_terms: list[str] = field(default_factory=list)     # == weak_terms
    # ── new tiers ─────────────────────────────────────────────────────────────
    support_terms: list[str] = field(default_factory=list)
    negative_terms: list[str] = field(default_factory=list)
    # ── facet / constraint metadata ───────────────────────────────────────────
    intent_facets: dict = field(default_factory=dict)
    query_constraints: dict = field(default_factory=dict)
    # ── existing metadata ─────────────────────────────────────────────────────
    semantic_tags: list[str] = field(default_factory=list)
    intent: str = "semantic_photo_search"
    search_mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    filters: dict = field(default_factory=dict)
    # Generic, validated query controls. Legacy fixed filters remain above for
    # compatibility with existing planners and filter policy.
    filter_clauses: list[dict] = field(default_factory=list)
    sort: list[dict] = field(default_factory=list)
    recommended_profile: str = "default_semantic"
    penalize_tags: list[str] = field(default_factory=list)
    # ── debug / explain ───────────────────────────────────────────────────────
    # which tiered dict keys were found in the (cleaned) query
    matched_keys: list[str] = field(default_factory=list)
    # normalized concept anchors for concept recall (e.g. 动物/宠物)
    concept_terms: list[str] = field(default_factory=list)
    # facets that are "core" (derived from exact/strong match to a tiered key)
    core_facets: list[str] = field(default_factory=list)
    # Pack-derived positive / negative evidence terms consumed by filter policy.
    core_facet_evidence: dict = field(default_factory=dict)
    # ── EXIF / Photo metadata filters (parsed from query) ─────────────────────
    metadata_filters: dict = field(default_factory=dict)
    # ── Query planner diagnostics (LLM vs fallback) ───────────────────────────
    planner_debug: dict = field(default_factory=dict)
    # ── V2 planner contract carried through the legacy execution adapter ─────
    planner_contract_version: str = "1"
    planner_filters: dict = field(default_factory=dict)
    lexical_plan: dict = field(default_factory=dict)
    semantic_plan: dict = field(default_factory=dict)
    visual_plan: dict = field(default_factory=dict)
    unresolved_entities: dict = field(default_factory=dict)

    # ── convenience aliases ───────────────────────────────────────────────────

    @property
    def must_terms(self) -> list[str]:
        """Alias for exact_terms."""
        return self.exact_terms

    @property
    def strong_terms(self) -> list[str]:
        """Alias for expanded_terms."""
        return self.expanded_terms

    @property
    def weak_terms(self) -> list[str]:
        """Alias for broad_terms."""
        return self.broad_terms

    @property
    def all_terms(self) -> list[str]:
        """Union of all positive tiers (deduplicated, order-preserving)."""
        seen: set[str] = set()
        result: list[str] = []
        for term in (
            self.exact_terms
            + self.expanded_terms
            + self.support_terms
            + self.broad_terms
        ):
            tl = term.lower()
            if tl not in seen:
                seen.add(tl)
                result.append(term)
        return result

    @property
    def recall_terms(self) -> list[str]:
        """Terms that MAY trigger keyword recall: exact + expanded (strong) only.

        support_terms, broad_terms and negative_terms are excluded from recall.
        Support terms may only boost scores of photos already recalled by
        stronger evidence (exact or expanded).
        """
        seen: set[str] = set()
        result: list[str] = []
        for term in self.exact_terms + self.expanded_terms:
            tl = term.lower()
            if tl not in seen:
                seen.add(tl)
                result.append(term)
        return result


# ── Public entry point ────────────────────────────────────────────────────────

def understand_query(
    query: str,
    project_id: Optional[int] = None,
    concept_taxonomy: Optional[list[dict]] = None,
    rule_base_pack_id: Optional[str] = None,
    rule_extension_pack_ids: Optional[list[str]] = None,
) -> SearchQueryPlan:
    """Analyse a user search query and return a structured plan (rule engine)."""
    original_query = query.strip()
    if not original_query:
        return SearchQueryPlan(original_query=original_query, normalized_query=original_query)

    semantic_residual, filter_clauses, sort_specs = _parse_dynamic_query_controls(original_query)

    # Clean Chinese noise words BEFORE tokenisation so they don't become
    # spurious exact_terms (e.g. "的照片" should not end up in exact_terms).
    has_dynamic_controls = bool(filter_clauses or sort_specs)
    query = _clean_chinese_query(
        semantic_residual if has_dynamic_controls else original_query
    )

    extension_pack_ids = normalise_extension_pack_ids(rule_extension_pack_ids)
    rule_set = build_rule_set(
        str(rule_base_pack_id or DEFAULT_BASE_PACK_ID).strip(),
        extension_pack_ids,
    )
    runtime_rules = _build_rule_runtime(rule_set)

    search_mode: Literal["keyword", "vector", "hybrid"] = (
        "keyword" if _is_ocr_intent(query) else "hybrid"
    )
    intent = _classify_intent(query, runtime_rules)
    profile = _recommended_profile(intent)
    q_lower = query.lower()

    # Exact terms: words from the *cleaned* query
    exact_terms: list[str] = [w for w in query.split() if w]
    exact_lower: set[str] = {t.lower() for t in exact_terms}

    # Collect terms from all tiers of matched tiered-dict entries
    expanded_set: set[str] = set()   # strong (= expanded)
    support_set: set[str] = set()    # context clues (new tier)
    broad_set: set[str] = set()      # weak (= broad)
    negative_set: set[str] = set()   # conflict terms (new tier)

    # intent_facets: facet → list of associated terms from the query
    facet_terms: dict[str, list[str]] = {}  # facet → terms
    matched_keys_set: list[str] = []  # tiered dict keys found in cleaned query
    core_facet_evidence_map: dict[str, dict[str, set[str]]] = {
        "night": {
            "positive_terms": set(),
            "negative_terms": set(),
        },
        "indoor": {
            "positive_terms": set(),
            "negative_terms": set(),
            "query_triggers": set(),
        },
        "animal": {
            "positive_terms": set(),
            "negative_terms": set(),
            "generic_terms": set(),
            "entity_hints": set(),
            "weak_scene_terms": set(),
        },
    }

    for primary_facet, tiered_dict in runtime_rules.all_tiered_dicts_with_facets:
        for key, tiers in tiered_dict.items():
            if not _term_in_query(key, q_lower):
                continue
            if key not in matched_keys_set:
                matched_keys_set.append(key)

            # For Chinese substring queries, the matched key itself often carries
            # the real search intent even when the whole query has no spaces.
            # Treat the key as a strong recall term unless it is already explicit.
            if key.lower() not in exact_lower:
                expanded_set.add(key)

            # The entry's explicit facets override the dict-level primary_facet
            entry_facets: list[str] = tiers.get("facets", [primary_facet])

            for fct in entry_facets:
                if fct not in facet_terms:
                    facet_terms[fct] = []
                if key not in facet_terms[fct]:
                    facet_terms[fct].append(key)

            for t in tiers.get("expanded", []):
                if t.lower() not in exact_lower:
                    expanded_set.add(t)
                    for fct in entry_facets:
                        facet_terms.setdefault(fct, [])
            for t in tiers.get("support", []):
                tl = t.lower()
                if tl not in exact_lower and t not in expanded_set:
                    support_set.add(t)
            for t in tiers.get("broad", []):
                tl = t.lower()
                if tl not in exact_lower and t not in expanded_set and t not in support_set:
                    broad_set.add(t)
            for t in tiers.get("negative", []):
                tl = t.lower()
                if tl not in exact_lower:
                    negative_set.add(t)
            evidence_domain: Optional[str] = None
            if "time" in entry_facets or "lighting" in entry_facets:
                evidence_domain = "night"
            elif tiered_dict is runtime_rules.indoor_terms_tiered:
                evidence_domain = "indoor"
            elif tiered_dict is runtime_rules.animal_terms_tiered:
                evidence_domain = "animal"

            if evidence_domain:
                for t in tiers.get("core_facet_positive", []):
                    if str(t).strip():
                        core_facet_evidence_map[evidence_domain]["positive_terms"].add(
                            str(t).strip()
                        )
                for t in tiers.get("core_facet_negative", []):
                    if str(t).strip():
                        core_facet_evidence_map[evidence_domain]["negative_terms"].add(
                            str(t).strip()
                        )
                if evidence_domain == "animal":
                    for t in tiers.get("core_facet_generic_terms", []):
                        if str(t).strip():
                            core_facet_evidence_map["animal"]["generic_terms"].add(
                                str(t).strip()
                            )
                    for t in tiers.get("core_facet_entity_hints", []):
                        if str(t).strip():
                            core_facet_evidence_map["animal"]["entity_hints"].add(
                                str(t).strip()
                            )
                    for t in tiers.get("core_facet_weak_scene_terms", []):
                        if str(t).strip():
                            core_facet_evidence_map["animal"]["weak_scene_terms"].add(
                                str(t).strip()
                            )
                if evidence_domain == "indoor":
                    triggers = tiers.get("core_facet_query_triggers") or [key]
                    for t in triggers:
                        if str(t).strip():
                            core_facet_evidence_map["indoor"]["query_triggers"].add(
                                str(t).strip()
                            )

    # Apply project-level concept taxonomy after built-in dictionaries.
    normalized_concept_taxonomy = _normalise_concept_taxonomy(
        concept_taxonomy,
        default_taxonomy=list(rule_set.concept_taxonomy),
    )
    concept_terms = _apply_concept_taxonomy(
        query_lower=q_lower,
        exact_lower=exact_lower,
        expanded_set=expanded_set,
        broad_set=broad_set,
        matched_keys_set=matched_keys_set,
        concept_taxonomy=normalized_concept_taxonomy,
    )

    if intent in ("people_search", "group_photo_search"):
        people_concept_candidates = [
            "人物", "单人照", "人像", "多人", "合照", "合影", "集体照", "自拍", "全家福",
        ]
        for term in people_concept_candidates:
            if term.lower() in q_lower and term not in concept_terms:
                concept_terms.append(term)
        for term in exact_terms + list(expanded_set) + list(broad_set):
            text = str(term).strip()
            if text in people_concept_candidates and text not in concept_terms:
                concept_terms.append(text)

    expanded_terms = sorted(t for t in expanded_set)
    support_terms = sorted(t for t in support_set if t not in expanded_set)
    broad_terms = sorted(t for t in broad_set if t not in expanded_set and t not in support_set)
    negative_terms = sorted(t for t in negative_set)

    # Light mode for generic semantic queries: keep exact terms as anchor,
    # preserve only a few high-value expansions, and avoid broad/support over-expansion.
    if intent == "semantic_photo_search":
        expanded_terms = expanded_terms[:_LIGHT_QUERY_MAX_EXPANDED_TERMS]
        support_terms = []
        broad_terms = []
        negative_terms = [
            t for t in negative_terms if t in _LIGHT_NEGATIVE_ALLOWLIST
        ]

    # intent_facets: deduplicate term lists per facet
    intent_facets: dict[str, list[str]] = {}
    for fct, terms in facet_terms.items():
        seen_f: set[str] = set()
        deduped_f: list[str] = []
        for t in terms:
            if t.lower() not in seen_f:
                seen_f.add(t.lower())
                deduped_f.append(t)
        intent_facets[fct] = deduped_f

    # Core facets: derived from must (exact) + strong (expanded) term matches
    core_facets: list[str] = []
    if intent_facets:
        # facets from entries whose key appears in exact_terms are "core"
        for primary_facet, tiered_dict in runtime_rules.all_tiered_dicts_with_facets:
            for key, tiers in tiered_dict.items():
                if _term_in_query(key, q_lower):
                    entry_facets_core = tiers.get("facets", [primary_facet])
                    for fct in entry_facets_core:
                        if fct not in core_facets:
                            core_facets.append(fct)

    # Ensure animal facet evidence has stable defaults for entity-vs-generic checks.
    if intent == "animal_search":
        animal_evidence = core_facet_evidence_map["animal"]
        animal_evidence["generic_terms"].update(_ANIMAL_CATEGORY_TERMS)
        if not animal_evidence["entity_hints"]:
            for term in expanded_set:
                text = str(term).strip()
                if text and text not in _ANIMAL_CATEGORY_TERMS:
                    animal_evidence["entity_hints"].add(text)

    core_facet_evidence: dict = {}
    for domain, payload in core_facet_evidence_map.items():
        positive_terms = sorted(payload.get("positive_terms") or set())
        negative_terms = sorted(payload.get("negative_terms") or set())
        generic_terms = sorted(payload.get("generic_terms") or set())
        entity_hints = sorted(payload.get("entity_hints") or set())
        weak_scene_terms = sorted(payload.get("weak_scene_terms") or set())
        query_triggers = sorted(payload.get("query_triggers") or set())

        if not (
            positive_terms
            or negative_terms
            or generic_terms
            or entity_hints
            or weak_scene_terms
            or query_triggers
        ):
            continue

        core_facet_evidence[domain] = {
            "positive_terms": positive_terms,
            "negative_terms": negative_terms,
        }
        if generic_terms:
            core_facet_evidence[domain]["generic_terms"] = generic_terms
        if entity_hints:
            core_facet_evidence[domain]["entity_hints"] = entity_hints
        if weak_scene_terms:
            core_facet_evidence[domain]["weak_scene_terms"] = weak_scene_terms
        if query_triggers:
            core_facet_evidence[domain]["query_triggers"] = query_triggers

    # Keep flat fields for backward compatibility with existing callers.
    if "night" in core_facet_evidence:
        core_facet_evidence["positive_terms"] = list(
            core_facet_evidence["night"].get("positive_terms") or []
        )
        core_facet_evidence["negative_terms"] = list(
            core_facet_evidence["night"].get("negative_terms") or []
        )

    # Normalised query = all terms joined (for vector embedding)
    all_for_norm: list[str] = exact_terms + expanded_terms + support_terms + broad_terms
    seen_n: set[str] = set()
    deduped: list[str] = []
    for t in all_for_norm:
        if t.lower() not in seen_n:
            seen_n.add(t.lower())
            deduped.append(t)
    normalized_query = " ".join(deduped) if deduped else query
    semantic_query_text = _build_semantic_query_text(
        original_query=original_query,
        intent=intent,
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        broad_terms=broad_terms,
    )
    if has_dynamic_controls and not query:
        semantic_query_text = ""

    semantic_tags: list[str] = {
        "animal_search": ["动物", "宠物", "野生动物"],
        "weather_search": ["天气", "自然"],
        "activity_search": ["户外", "自然", "旅行"],
        "people_search": ["人物", "生活"],
        "group_photo_search": ["人物", "多人", "合照"],
        "food_search": ["美食", "生活"],
        "location_search": ["地点", "旅行", "风景"],
        "metadata_location_search": ["地点", "地址", "位置"],
    }.get(intent, [])

    filters = _infer_filters(query, intent, runtime_rules)
    penalize_tags = _build_penalize_tags(intent, filters)

    metadata_filters = _parse_metadata_filters(original_query)
    if intent in _METADATA_ONLY_BLOCKED_INTENTS:
        metadata_filters["metadata_only"] = False

    if (
        metadata_filters.get("metadata_only")
        and metadata_filters.get("place_terms")
        and _has_location_query_cue(original_query)
    ):
        intent = "metadata_location_search"
        exact_terms = _dedupe_terms(list(metadata_filters.get("place_terms") or []))
        expanded_terms = []
        support_terms = []
        broad_terms = []
        negative_terms = []
        normalized_query = " ".join(exact_terms) if exact_terms else original_query
        semantic_query_text = ""
        profile = _recommended_profile(intent)

    # query_constraints: per-query evidence requirements (can be project-overridden later)
    query_constraints: dict = {
        "requires_visual_evidence": True,
        "allow_weak_only_match": False,
        "min_evidence_level": "C",
        "query_core_facets": core_facets,
    }
    if intent == "metadata_location_search":
        query_constraints["requires_visual_evidence"] = False
        query_constraints["allow_weak_only_match"] = False
        query_constraints["requires_metadata_evidence"] = True
        query_constraints["allow_vector_only_match"] = False
        query_constraints["min_metadata_match"] = "exact_or_contains"
        query_constraints["min_evidence_level"] = "A"

    # Pure metadata/time queries should not be forced to carry keyword visual evidence,
    # otherwise hybrid post-filter can drop all vector-only candidates.
    if bool(metadata_filters.get("metadata_only")) and intent != "metadata_location_search":
        query_constraints["requires_visual_evidence"] = False
        query_constraints["allow_weak_only_match"] = True

    return SearchQueryPlan(
        original_query=original_query,
        normalized_query=normalized_query,
        semantic_query_text=semantic_query_text,
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        support_terms=support_terms,
        broad_terms=broad_terms,
        negative_terms=negative_terms,
        intent_facets=intent_facets,
        query_constraints=query_constraints,
        semantic_tags=semantic_tags,
        intent=intent,
        search_mode=search_mode,
        filters=filters,
        filter_clauses=filter_clauses,
        sort=sort_specs,
        recommended_profile=profile,
        penalize_tags=penalize_tags,
        matched_keys=matched_keys_set,
        concept_terms=concept_terms,
        core_facets=core_facets,
        core_facet_evidence=core_facet_evidence,
        metadata_filters=metadata_filters,
    )


def _build_penalize_tags(intent: str, filters: dict) -> list[str]:
    """Return intent-specific tags to penalise in semantic_tag_boost."""
    if intent == "weather_search":
        weather = filters.get("weather")
        if weather == "rain":
            return list(_PENALIZE_TAGS_RAIN)
        if weather == "snow":
            return list(_PENALIZE_TAGS_SNOW)
        # sunny / generic weather
        if weather in ("sunny",):
            return list(_PENALIZE_TAGS_SUNNY)
    return []
