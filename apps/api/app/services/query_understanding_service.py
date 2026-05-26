"""Rule-based query understanding service.

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
from typing import Any, Dict, Literal, Optional, TypedDict

from .query_understanding_dictionaries import ANIMAL_TERMS_TIERED, WEATHER_TERMS_TIERED

_WEATHER_TERMS_TIERED = WEATHER_TERMS_TIERED
_ANIMAL_TERMS_TIERED = ANIMAL_TERMS_TIERED

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
    r"的照片|的相片|的图片|的图|照片|相片|图片|[的了在里中是]|拍的|拍摄|摄影|帮我找|搜索|找|查"
)
_PLACE_SPLIT_RE = re.compile(r"[\s,/，、]+")
_GENERIC_NON_PLACE_TERMS: frozenset[str] = frozenset({
    "夜景", "夜晚", "室内", "室外", "风景", "美食", "食物", "人物", "建筑", "街景",
    "动物", "宠物", "野生动物", "小动物", "猫", "狗", "鸟", "马", "鹿", "兔", "兔子", "鱼",
    "下雨天", "晴天", "雪天", "海边", "日落", "日出", "晚霞", "自拍",
})

# Strong semantic intents should never be treated as metadata-only requests,
# even if metadata parser matched some tokens.
_METADATA_ONLY_BLOCKED_INTENTS: frozenset[str] = frozenset({
    "animal_search",
    "people_search",
    "group_photo_search",
    "food_search",
    "weather_search",
    "activity_search",
    "semantic_photo_search",
})

_ANIMAL_CATEGORY_TERMS: frozenset[str] = frozenset({
    "动物", "宠物", "野生动物", "动物园", "小动物", "animal",
})

_DEFAULT_CONCEPT_TAXONOMY: list[dict[str, object]] = [
    {
        "concept": "动物",
        "children": ["猫", "狗", "鸟", "马", "鹿", "兔子", "鱼"],
        "aliases": ["animal", "小动物", "宠物"],
        "positive_fields": ["object_tags", "search_keywords", "raw_result.animals"],
        "negative_terms": [],
        "recall_policy": "expand_children",
        "evidence_policy": "require_child_entity_or_high_vector",
    }
]


def _normalise_concept_taxonomy(raw: Optional[list[dict]]) -> list[dict[str, object]]:
    if not raw:
        return list(_DEFAULT_CONCEPT_TAXONOMY)

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
    return normalized or list(_DEFAULT_CONCEPT_TAXONOMY)


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
        recall_policy = str(entry.get("recall_policy") or "expand_children").strip()

        concept_matched = concept.lower() in query_lower
        alias_matched = any(alias.lower() in query_lower for alias in aliases)
        child_matched = any(child.lower() in query_lower for child in children)
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
        (r"\biphone\b", "Apple", "iPhone"),
        (r"\bapple\b|苹果手机", "Apple", None),
        (r"\bsony\b|索尼", "Sony", None),
        (r"\bcanon\b|佳能", "Canon", None),
        (r"\bnikon\b|尼康", "Nikon", None),
        (r"\bdji\b|大疆", "DJI", None),
        (r"\bhuawei\b|华为", "Huawei", None),
        (r"\bsamsung\b|三星", "Samsung", None),
        (r"\bfuji(?:film)?\b|富士", "FUJIFILM", None),
        (r"\bpanasonic\b|松下", "Panasonic", None),
        (r"\bolympus\b|奥林巴斯", "Olympus", None),
        (r"\bleica\b|徕卡", "Leica", None),
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
    cleaned_remaining = _META_NOISE_RE.sub("", remaining).strip()
    place_terms: list[str] = []
    if cleaned_remaining:
        for raw_term in _PLACE_SPLIT_RE.split(cleaned_remaining):
            term = raw_term.strip()
            if not term or term in _GENERIC_NON_PLACE_TERMS:
                continue
            if term not in place_terms:
                place_terms.append(term)
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


# ── Tiered expansion dictionaries ─────────────────────────────────────────────
#
# Each entry may contain these keys (all optional except expanded/broad):
#   expanded  — strong synonyms that can independently recall (scored × 0.7)
#   support   — context clues that need combination (scored × 0.5, no recall)
#   broad     — weak category terms, boost-only (scored × 0.3, no recall)
#   negative  — conflicting terms; photos matching these are penalised
#   facets    — list of primary intent facets (e.g. ["time", "lighting"])

class _TieredTerms(TypedDict, total=False):
    expanded: list
    support: list
    broad: list
    negative: list
    facets: list


_OUTDOOR_TERMS_TIERED: Dict[str, Any] = {
    "爬山": {
        "expanded": ["登山", "徒步", "山路"],
        "support": ["山顶", "山峰", "登山杖", "背包"],
        "broad": ["户外", "自然"],
        "negative": ["室内", "城市", "海边"],
        "facets": ["activity", "scene"],
    },
    "登山": {
        "expanded": ["爬山", "徒步", "山路"],
        "support": ["山顶", "山峰", "背包"],
        "broad": ["户外", "自然"],
        "negative": ["室内", "城市"],
        "facets": ["activity", "scene"],
    },
    "徒步": {
        "expanded": ["登山", "山路", "步道"],
        "support": ["背包", "登山杖"],
        "broad": ["户外", "自然"],
        "facets": ["activity"],
    },
    "户外": {
        "expanded": ["自然", "山地", "步道", "草地", "树林"],
        "broad": [],
        "facets": ["scene"],
    },
    "山顶": {
        "expanded": ["山峰", "登山", "爬山"],
        "broad": ["远眺"],
        "facets": ["scene"],
    },
    "山峰": {
        "expanded": ["山顶", "登山", "爬山"],
        "broad": ["壮观"],
        "facets": ["scene"],
    },
    "步道": {
        "expanded": ["徒步", "山路", "登山"],
        "broad": ["户外"],
        "facets": ["activity"],
    },
    "远足": {
        "expanded": ["徒步", "户外", "山路"],
        "broad": ["背包"],
        "facets": ["activity"],
    },
    "hiking": {
        "expanded": ["徒步", "登山"],
        "support": ["背包", "登山杖"],
        "broad": ["户外", "山路"],
        "facets": ["activity"],
    },
    "山": {
        "expanded": ["山地", "山峰", "山顶"],
        "broad": ["户外", "自然"],
        "facets": ["scene"],
    },
}

_PEOPLE_TERMS_TIERED: Dict[str, Any] = {
    "爸爸": {
        "expanded": ["父亲", "家庭", "亲子", "合影"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "父亲": {
        "expanded": ["爸爸", "家庭", "亲子", "合影"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "妈妈": {
        "expanded": ["母亲", "家庭", "亲子", "合影"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "母亲": {
        "expanded": ["妈妈", "家庭", "亲子", "合影"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "女儿": {
        "expanded": ["孩子", "儿童", "亲子", "家庭"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "儿子": {
        "expanded": ["孩子", "儿童", "亲子", "家庭"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "亲子": {
        "expanded": ["家庭", "父母", "孩子", "合影"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "一家人": {
        "expanded": ["家庭", "亲子", "合影", "多人"],
        "broad": ["人物", "生活"],
        "facets": ["people"],
    },
    "孩子": {
        "expanded": ["小孩", "儿童", "玩耍"],
        "broad": ["童年", "幼儿"],
        "facets": ["people"],
    },
    "儿童": {
        "expanded": ["孩子", "小孩", "玩耍"],
        "broad": [],
        "facets": ["people"],
    },
    "小孩": {
        "expanded": ["孩子", "儿童", "玩耍"],
        "broad": [],
        "facets": ["people"],
    },
    "婴儿": {
        "expanded": ["宝宝", "小孩"],
        "broad": ["孩子"],
        "facets": ["people"],
    },
    "老人": {
        "expanded": ["长辈", "老年人"],
        "broad": [],
        "facets": ["people"],
    },
    "全家福": {
        "expanded": ["家庭", "合影", "多人"],
        "broad": [],
        "facets": ["people", "group_photo"],
    },
    "自拍": {
        "expanded": ["selfie", "单人"],
        "broad": [],
        "facets": ["people"],
    },
    "合照": {
        "expanded": ["合影", "集体照", "多人", "多人合照", "人物"],
        "broad": ["集体"],
        "facets": ["people", "group_photo"],
    },
    "合影": {
        "expanded": ["合照", "集体照", "多人", "多人合影"],
        "broad": ["集体"],
        "facets": ["people", "group_photo"],
    },
    "集体照": {
        "expanded": ["合照", "合影", "多人", "集体"],
        "broad": ["人物"],
        "facets": ["people", "group_photo"],
    },
    "多人": {
        "expanded": ["合照", "合影", "集体照", "多人合照", "多人合影"],
        "broad": ["人物", "集体"],
        "facets": ["people", "group_photo"],
    },
    "多人合照": {
        "expanded": ["合照", "合影", "多人", "集体照"],
        "broad": ["人物", "集体"],
        "facets": ["people", "group_photo"],
    },
    "多人合影": {
        "expanded": ["合影", "合照", "多人", "集体照"],
        "broad": ["人物", "集体"],
        "facets": ["people", "group_photo"],
    },
    "group photo": {
        "expanded": ["合照", "合影", "集体照", "多人"],
        "broad": ["人物"],
        "facets": ["people", "group_photo"],
    },
}

_FOOD_TERMS_TIERED: Dict[str, Any] = {
    "食物": {
        "expanded": ["美食", "饭菜", "料理"],
        "broad": ["餐厅"],
        "facets": ["object"],
    },
    "美食": {
        "expanded": ["食物", "料理", "饭菜"],
        "broad": [],
        "facets": ["object"],
    },
    "餐厅": {
        "expanded": ["饭馆", "美食", "食物"],
        "broad": [],
        "facets": ["scene", "object"],
    },
    "咖啡": {
        "expanded": ["coffee", "咖啡馆"],
        "broad": ["饮品"],
        "facets": ["object"],
    },
    "甜点": {
        "expanded": ["蛋糕", "甜食"],
        "broad": ["美食"],
        "facets": ["object"],
    },
}

_TRAVEL_TERMS_TIERED: Dict[str, Any] = {
    "旅行": {
        "expanded": ["旅游", "出行"],
        "broad": ["风景", "景点"],
        "facets": ["activity", "scene"],
    },
    "旅游": {
        "expanded": ["旅行", "出行"],
        "broad": ["风景", "景点"],
        "facets": ["activity", "scene"],
    },
    "海边": {
        "expanded": ["海滩", "海岸", "海浪", "大海", "沙滩"],
        "broad": [],
        "negative": ["室内", "山地"],
        "facets": ["scene", "location"],
    },
    "沙滩": {
        "expanded": ["海边", "海滩", "海浪"],
        "broad": ["大海"],
        "facets": ["scene", "location"],
    },
    "大海": {
        "expanded": ["海洋", "海边", "海浪"],
        "broad": ["海景"],
        "facets": ["scene", "location"],
    },
    "海洋": {
        "expanded": ["大海", "海边", "海浪"],
        "broad": [],
        "facets": ["scene"],
    },
    "城市": {
        "expanded": ["街道", "建筑", "都市"],
        "support": ["地标", "广场", "商业区"],
        "broad": ["行人"],
        "facets": ["scene", "location"],
    },
    "建筑": {
        "expanded": ["楼房", "高楼", "城市"],
        "broad": ["结构"],
        "facets": ["scene", "object"],
    },
    "风景": {
        "expanded": ["自然", "景色"],
        "broad": ["户外"],
        "facets": ["scene"],
    },
    # Time / lighting terms — core facets: time + lighting
    "日落": {
        "expanded": ["黄昏", "夕阳", "晚霞"],
        "support": ["橙色天空", "暖色调"],
        "broad": ["天空"],
        "negative": ["夜晚", "夜色", "黑暗"],
        "facets": ["time", "lighting"],
    },
    "日出": {
        "expanded": ["清晨", "朝霞", "晨光"],
        "support": ["橙色天空", "暖色调"],
        "broad": ["天空"],
        "negative": ["夜晚", "夜色", "黑暗"],
        "facets": ["time", "lighting"],
    },
    "夜景": {
        "expanded": ["夜晚", "夜色", "晚上", "夜间"],
        "support": ["灯光", "霓虹", "路灯", "暗光", "长曝光"],
        "broad": ["城市", "建筑", "街道", "地标"],
        "negative": ["白天", "日间", "阳光", "晴天"],
        "facets": ["time", "lighting"],
    },
    "夜晚": {
        "expanded": ["夜景", "夜色", "晚上", "夜间", "黑夜"],
        "support": ["灯光", "霓虹", "路灯", "暗光", "长曝光"],
        "broad": ["城市", "建筑", "街道"],
        "negative": ["白天", "日间", "阳光", "晴天"],
        "facets": ["time", "lighting"],
    },
    "晚上": {
        "expanded": ["夜晚", "夜景", "夜色", "夜间"],
        "support": ["灯光", "霓虹", "路灯", "暗光"],
        "broad": ["城市", "街道"],
        "negative": ["白天", "日间", "阳光", "晴天"],
        "facets": ["time", "lighting"],
    },
    "黑夜": {
        "expanded": ["夜晚", "夜景", "夜色"],
        "support": ["灯光", "暗光", "路灯"],
        "broad": ["城市"],
        "negative": ["白天", "阳光", "晴天"],
        "facets": ["time", "lighting"],
    },
    "夜间": {
        "expanded": ["夜晚", "夜景", "夜色", "晚上"],
        "support": ["灯光", "霓虹", "路灯", "暗光"],
        "broad": ["城市", "建筑"],
        "negative": ["白天", "日间", "阳光", "晴天"],
        "facets": ["time", "lighting"],
    },
    "sunset": {
        "expanded": ["日落", "黄昏", "夕阳", "晚霞"],
        "broad": [],
        "negative": ["夜晚", "黑暗"],
        "facets": ["time", "lighting"],
    },
    "sunrise": {
        "expanded": ["日出", "清晨", "朝霞"],
        "broad": [],
        "negative": ["夜晚", "黑暗"],
        "facets": ["time", "lighting"],
    },
}

_INDOOR_TERMS_TIERED: Dict[str, Any] = {
    "室内": {
        "expanded": ["客厅", "卧室", "厨房", "房间", "家具"],
        "support": ["家", "家庭", "屋内"],
        "broad": [],
        "negative": ["户外", "自然", "海边"],
        "facets": ["scene"],
    },
    "家": {
        "expanded": ["室内", "客厅", "卧室"],
        "support": ["家庭", "生活"],
        "broad": ["家具"],
        "facets": ["scene"],
    },
    "客厅": {
        "expanded": ["沙发", "室内"],
        "broad": ["家"],
        "facets": ["scene"],
    },
    "卧室": {
        "expanded": ["床", "室内"],
        "broad": ["家"],
        "facets": ["scene"],
    },
    "厨房": {
        "expanded": ["烹饪", "室内"],
        "broad": ["家"],
        "facets": ["scene"],
    },
    "图书馆": {
        "expanded": ["书架", "阅读"],
        "broad": ["室内"],
        "facets": ["scene"],
    },
    "博物馆": {
        "expanded": ["展览", "展品"],
        "broad": ["室内"],
        "facets": ["scene"],
    },
}

_OUTDOOR_KEYS = set(_OUTDOOR_TERMS_TIERED.keys())
_WEATHER_KEYS = set(_WEATHER_TERMS_TIERED.keys())
_ANIMAL_KEYS = set(_ANIMAL_TERMS_TIERED.keys())
_PEOPLE_KEYS = set(_PEOPLE_TERMS_TIERED.keys())
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
_FOOD_KEYS = set(_FOOD_TERMS_TIERED.keys())
_TRAVEL_KEYS = set(_TRAVEL_TERMS_TIERED.keys())
_INDOOR_KEYS = set(_INDOOR_TERMS_TIERED.keys())

# (primary_facet, dict) — used to derive intent_facets in understand_query
_ALL_TIERED_DICTS_WITH_FACETS: list = [
    ("activity", _OUTDOOR_TERMS_TIERED),
    ("weather", _WEATHER_TERMS_TIERED),
    ("object", _ANIMAL_TERMS_TIERED),
    ("people", _PEOPLE_TERMS_TIERED),
    ("object", _FOOD_TERMS_TIERED),
    ("scene", _TRAVEL_TERMS_TIERED),
    ("scene", _INDOOR_TERMS_TIERED),
]

# Backward-compat tuple (order preserved)
_ALL_TIERED_DICTS: tuple = tuple(d for _, d in _ALL_TIERED_DICTS_WITH_FACETS)


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


def _classify_intent(query: str) -> str:
    if _is_ocr_intent(query):
        return "ocr_text_search"
    q_lower = query.lower()
    for key in _ANIMAL_KEYS:
        if key in q_lower:
            return "animal_search"
    for key in _WEATHER_KEYS:
        if key in q_lower:
            return "weather_search"
    for key in _OUTDOOR_KEYS:
        if key in q_lower:
            return "activity_search"
    if any(k in q_lower for k in _GROUP_PHOTO_KEYS):
        return "group_photo_search"
    if any(k in q_lower for k in _PEOPLE_KEYS):
        return "people_search"
    if any(k in q_lower for k in _FOOD_KEYS):
        return "food_search"
    if any(k in q_lower for k in _TRAVEL_KEYS):
        return "location_search"
    return "semantic_photo_search"


def _recommended_profile(intent: str) -> str:
    return {
        "animal_search": "entity_object",
        "ocr_text_search": "ocr_text",
        "activity_search": "activity_scene",
        "location_search": "location_time",
        "people_search": "people_group",
        "group_photo_search": "people_group",
    }.get(intent, "default_semantic")


# ── Filter inference ──────────────────────────────────────────────────────────

def _infer_filters(query: str, intent: str) -> dict:
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

    if any(k in q_lower for k in _OUTDOOR_KEYS):
        filters["indoor_outdoor"] = "outdoor"
    elif any(k in q_lower for k in _INDOOR_KEYS):
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
    recommended_profile: str = "default_semantic"
    penalize_tags: list[str] = field(default_factory=list)
    # ── debug / explain ───────────────────────────────────────────────────────
    # which tiered dict keys were found in the (cleaned) query
    matched_keys: list[str] = field(default_factory=list)
    # normalized concept anchors for concept recall (e.g. 动物/宠物)
    concept_terms: list[str] = field(default_factory=list)
    # facets that are "core" (derived from exact/strong match to a tiered key)
    core_facets: list[str] = field(default_factory=list)
    # ── EXIF / Photo metadata filters (parsed from query) ─────────────────────
    metadata_filters: dict = field(default_factory=dict)

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
) -> SearchQueryPlan:
    """Analyse a user search query and return a structured plan (rule engine)."""
    original_query = query.strip()
    if not original_query:
        return SearchQueryPlan(original_query=original_query, normalized_query=original_query)

    # Clean Chinese noise words BEFORE tokenisation so they don't become
    # spurious exact_terms (e.g. "的照片" should not end up in exact_terms).
    query = _clean_chinese_query(original_query)

    search_mode: Literal["keyword", "vector", "hybrid"] = (
        "keyword" if _is_ocr_intent(query) else "hybrid"
    )
    intent = _classify_intent(query)
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

    for primary_facet, tiered_dict in _ALL_TIERED_DICTS_WITH_FACETS:
        for key, tiers in tiered_dict.items():
            if key not in q_lower:
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

    # Apply project-level concept taxonomy after built-in dictionaries.
    normalized_concept_taxonomy = _normalise_concept_taxonomy(concept_taxonomy)
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
        for primary_facet, tiered_dict in _ALL_TIERED_DICTS_WITH_FACETS:
            for key, tiers in tiered_dict.items():
                if key in q_lower:
                    entry_facets_core = tiers.get("facets", [primary_facet])
                    for fct in entry_facets_core:
                        if fct not in core_facets:
                            core_facets.append(fct)

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

    semantic_tags: list[str] = {
        "animal_search": ["动物", "宠物", "野生动物"],
        "weather_search": ["天气", "自然"],
        "activity_search": ["户外", "自然", "旅行"],
        "people_search": ["人物", "生活"],
        "group_photo_search": ["人物", "多人", "合照"],
        "food_search": ["美食", "生活"],
        "location_search": ["地点", "旅行", "风景"],
    }.get(intent, [])

    filters = _infer_filters(query, intent)
    penalize_tags = _build_penalize_tags(intent, filters)

    # query_constraints: per-query evidence requirements (can be project-overridden later)
    query_constraints: dict = {
        "requires_visual_evidence": True,
        "allow_weak_only_match": False,
        "min_evidence_level": "C",
        "query_core_facets": core_facets,
    }

    metadata_filters = _parse_metadata_filters(original_query)
    if intent in _METADATA_ONLY_BLOCKED_INTENTS:
        metadata_filters["metadata_only"] = False

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
        recommended_profile=profile,
        penalize_tags=penalize_tags,
        matched_keys=matched_keys_set,
        concept_terms=concept_terms,
        core_facets=core_facets,
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
