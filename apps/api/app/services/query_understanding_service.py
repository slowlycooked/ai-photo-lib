"""Rule-based query understanding service.

Converts a user's natural language search query into a structured SearchQueryPlan
that downstream search components can use for:
  - keyword expansion (more terms to match against)
  - intent-aware vector weight selection
  - filter inference (e.g. has_animals=True)

This is the first version: pure rule engine, no LLM call required.
A future version can swap in a DeepSeek/Qwen call while keeping the same
SearchQueryPlan interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


# ── Expansion dictionaries ────────────────────────────────────────────────────

# Each key is a query fragment that triggers expansion.
# Values are the expanded terms added to the normalised query.

_OUTDOOR_TERMS: dict[str, list[str]] = {
    "爬山": ["爬山", "登山", "徒步", "山路", "山顶", "山峰", "户外", "背包", "登山杖"],
    "登山": ["登山", "爬山", "徒步", "山路", "山顶", "山峰", "户外", "背包"],
    "徒步": ["徒步", "登山", "山路", "步道", "户外", "背包"],
    "户外": ["户外", "自然", "山地", "步道", "草地", "树林"],
    "山顶": ["山顶", "山峰", "登山", "爬山", "远眺"],
    "山峰": ["山峰", "山顶", "登山", "爬山", "壮观"],
    "步道": ["步道", "徒步", "山路", "登山", "户外"],
    "远足": ["远足", "徒步", "户外", "背包", "山路"],
    "hiking": ["徒步", "登山", "户外", "背包", "山路"],
    "山": ["山", "山地", "山峰", "山顶", "户外", "自然"],
}

_WEATHER_TERMS: dict[str, list[str]] = {
    "下雨": ["下雨", "雨天", "雨伞", "雨衣", "雨滴", "积水", "湿地面", "阴天"],
    "下雨天": ["下雨", "雨天", "雨伞", "雨衣", "雨滴", "积水", "湿地面", "阴天"],
    "雨天": ["雨天", "下雨", "雨伞", "雨滴", "积水", "阴天"],
    "下雪": ["下雪", "雪天", "雪地", "雪花", "积雪", "寒冷"],
    "雪天": ["雪天", "下雪", "雪地", "积雪", "寒冷"],
    "晴天": ["晴天", "阳光", "蓝天", "白云", "户外"],
    "出太阳": ["晴天", "阳光", "蓝天", "白云", "户外", "日照"],
    "太阳": ["晴天", "阳光", "蓝天", "白云", "户外", "日照"],
    "阳光": ["阳光", "晴天", "蓝天", "白云", "户外", "日照"],
    "晴朗": ["晴天", "阳光", "蓝天", "白云", "户外"],
    "阴天": ["阴天", "多云", "乌云", "灰色天空"],
    "大风": ["大风", "风大", "风吹", "户外", "飞扬"],
    "雨伞": ["雨伞", "下雨", "雨天", "防雨"],
    "rain": ["下雨", "雨天", "雨伞", "雨滴", "积水", "阴天"],
    "snow": ["下雪", "雪天", "雪地", "积雪"],
    "sunny": ["晴天", "阳光", "蓝天", "白云", "户外"],
    "sunshine": ["阳光", "晴天", "蓝天", "白云", "户外"],
}

_ANIMAL_TERMS: dict[str, list[str]] = {
    "动物": ["动物", "猫", "狗", "鸟", "马", "鹿", "宠物", "野生动物", "动物园"],
    "猫狗": ["猫", "狗", "宠物", "动物"],
    "猫": ["猫", "小猫", "猫咪", "宠物", "动物"],
    "狗": ["狗", "小狗", "狗狗", "宠物", "动物"],
    "鸟": ["鸟", "小鸟", "飞鸟", "禽鸟", "动物"],
    "宠物": ["宠物", "猫", "狗", "动物"],
    "野生动物": ["野生动物", "动物", "自然", "户外", "野外"],
    "动物园": ["动物园", "动物", "野生动物"],
    "马": ["马", "骏马", "骑马", "动物"],
    "鹿": ["鹿", "梅花鹿", "野鹿", "动物"],
    "兔子": ["兔子", "小兔", "宠物", "动物"],
    "鱼": ["鱼", "水族", "海洋", "动物"],
    "蝴蝶": ["蝴蝶", "昆虫", "花园", "动物"],
    "animal": ["动物", "猫", "狗", "鸟", "宠物", "野生动物"],
    "cat": ["猫", "小猫", "宠物", "动物"],
    "dog": ["狗", "小狗", "宠物", "动物"],
    "bird": ["鸟", "小鸟", "飞鸟", "动物"],
}

_PEOPLE_TERMS: dict[str, list[str]] = {
    "孩子": ["孩子", "小孩", "儿童", "玩耍", "童年", "幼儿"],
    "儿童": ["儿童", "孩子", "小孩", "玩耍"],
    "小孩": ["小孩", "孩子", "儿童", "玩耍"],
    "婴儿": ["婴儿", "宝宝", "小孩", "孩子"],
    "老人": ["老人", "长辈", "老年人"],
    "全家福": ["全家福", "家庭", "合影", "多人"],
    "自拍": ["自拍", "selfie", "单人"],
    "合影": ["合影", "集体照", "合照", "多人"],
}

_FOOD_TERMS: dict[str, list[str]] = {
    "食物": ["食物", "美食", "饭菜", "料理", "餐厅"],
    "美食": ["美食", "食物", "料理", "饭菜"],
    "餐厅": ["餐厅", "饭馆", "餐厅", "美食", "食物"],
    "咖啡": ["咖啡", "coffee", "咖啡馆", "饮品"],
    "甜点": ["甜点", "蛋糕", "甜食", "美食"],
}

_TRAVEL_TERMS: dict[str, list[str]] = {
    "旅行": ["旅行", "旅游", "出行", "风景", "景点"],
    "旅游": ["旅游", "旅行", "出行", "风景", "景点"],
    "海边": ["海边", "海滩", "海岸", "海浪", "大海", "沙滩"],
    "沙滩": ["沙滩", "海边", "海滩", "海浪", "大海"],
    "大海": ["大海", "海洋", "海边", "海浪", "海景"],
    "海洋": ["海洋", "大海", "海边", "海浪"],
    "城市": ["城市", "街道", "建筑", "都市", "夜景"],
    "建筑": ["建筑", "楼房", "高楼", "城市", "结构"],
    "风景": ["风景", "自然", "景色", "户外"],
    "日落": ["日落", "黄昏", "夕阳", "晚霞", "天空"],
    "日出": ["日出", "清晨", "朝霞", "天空", "晨光"],
    "夜景": ["夜景", "夜晚", "灯光", "城市", "夜色"],
    "sunset": ["日落", "黄昏", "夕阳", "晚霞"],
    "sunrise": ["日出", "清晨", "朝霞"],
}

_INDOOR_TERMS: dict[str, list[str]] = {
    "室内": ["室内", "家", "家庭", "客厅", "卧室"],
    "家": ["家", "室内", "家庭", "生活"],
    "客厅": ["客厅", "沙发", "室内", "家"],
    "卧室": ["卧室", "床", "室内", "家"],
    "厨房": ["厨房", "烹饪", "室内", "家"],
    "图书馆": ["图书馆", "书架", "阅读", "室内"],
    "博物馆": ["博物馆", "展览", "展品", "室内"],
}


# ── Intent classification ─────────────────────────────────────────────────────

# Keywords that indicate OCR / text-in-image search intent
_OCR_PATTERNS = re.compile(
    r"(order|invoice|id|sn|单号|订单|发票|金额|门牌|车牌|编号|号码|序列号)",
    flags=re.IGNORECASE,
)


def _is_ocr_intent(query: str) -> bool:
    if _OCR_PATTERNS.search(query):
        return True
    digit_count = sum(1 for ch in query if ch.isdigit())
    # Queries with 4+ consecutive digits are likely scanning for OCR codes/IDs
    if digit_count >= 4:
        return True
    # Queries that look like mixed alphanumeric codes (e.g. SN123456, ABC-999)
    # Only trigger if digits are present alongside letters — not for plain words
    if digit_count >= 1 and re.search(r"[A-Za-z]\d|\d[A-Za-z]", query):
        ascii_count = sum(1 for ch in query if ch.isascii() and ch.isalnum())
        if ascii_count >= max(6, len(query) // 2):
            return True
    return False


def _classify_intent(query: str, expanded_terms: list[str]) -> str:
    if _is_ocr_intent(query):
        return "ocr_text_search"

    q_lower = query.lower()
    all_text = q_lower + " " + " ".join(expanded_terms).lower()

    # Check from most specific to least specific
    animal_keys = set(_ANIMAL_TERMS.keys())
    weather_keys = set(_WEATHER_TERMS.keys())
    outdoor_keys = set(_OUTDOOR_TERMS.keys())

    for key in animal_keys:
        if key in q_lower:
            return "animal_search"
    for key in weather_keys:
        if key in q_lower:
            return "weather_search"
    for key in outdoor_keys:
        if key in q_lower:
            return "activity_search"

    # Fall through to generic
    if any(k in q_lower for k in _PEOPLE_TERMS):
        return "people_search"
    if any(k in q_lower for k in _FOOD_TERMS):
        return "food_search"
    if any(k in q_lower for k in _TRAVEL_TERMS):
        return "location_search"

    return "semantic_photo_search"


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

    q_lower = query.lower()
    if any(k in q_lower for k in _WEATHER_TERMS):
        for key in ("下雨", "rain", "雨天"):
            if key in q_lower:
                filters["weather"] = "rain"
                break
        for key in ("下雪", "snow", "雪天"):
            if key in q_lower:
                filters["weather"] = "snow"
                break

    if any(k in q_lower for k in _OUTDOOR_TERMS):
        filters["indoor_outdoor"] = "outdoor"
    elif any(k in q_lower for k in _INDOOR_TERMS):
        filters["indoor_outdoor"] = "indoor"

    if any(k in q_lower for k in ("日落", "sunset", "黄昏", "夕阳")):
        filters["time_of_day"] = "sunset"
    elif any(k in q_lower for k in ("日出", "sunrise", "清晨", "朝霞")):
        filters["time_of_day"] = "morning"
    elif any(k in q_lower for k in ("夜景", "夜晚", "夜色")):
        filters["time_of_day"] = "night"

    return filters


# ── Main dataclass and function ───────────────────────────────────────────────


@dataclass
class SearchQueryPlan:
    original_query: str
    normalized_query: str
    expanded_terms: list[str] = field(default_factory=list)
    semantic_tags: list[str] = field(default_factory=list)
    intent: str = "semantic_photo_search"
    search_mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    filters: dict = field(default_factory=dict)


def understand_query(
    query: str,
    project_id: Optional[int] = None,
) -> SearchQueryPlan:
    """Analyse a user search query and return a structured plan.

    Rules engine implementation — no LLM calls.
    """
    query = query.strip()
    if not query:
        return SearchQueryPlan(
            original_query=query,
            normalized_query=query,
        )

    # Determine search mode
    if _is_ocr_intent(query):
        search_mode: Literal["keyword", "vector", "hybrid"] = "keyword"
    else:
        search_mode = "hybrid"

    # Expand terms
    q_lower = query.lower()
    all_expansions: list[str] = []

    for expansion_dict in (
        _OUTDOOR_TERMS,
        _WEATHER_TERMS,
        _ANIMAL_TERMS,
        _PEOPLE_TERMS,
        _FOOD_TERMS,
        _TRAVEL_TERMS,
        _INDOOR_TERMS,
    ):
        for key, terms in expansion_dict.items():
            if key in q_lower:
                for term in terms:
                    if term not in all_expansions:
                        all_expansions.append(term)

    # Also add individual words from the original query if not already present
    for word in query.split():
        word = word.strip()
        if word and word not in all_expansions:
            all_expansions.append(word)

    # Remove duplicates while preserving order
    seen: set[str] = set()
    expanded_terms: list[str] = []
    for term in all_expansions:
        if term not in seen:
            seen.add(term)
            expanded_terms.append(term)

    # Build normalised query: original + expanded terms joined by space
    if expanded_terms:
        normalized_query = " ".join(expanded_terms)
    else:
        normalized_query = query

    # Classify intent
    intent = _classify_intent(query, expanded_terms)

    # Infer filters
    filters = _infer_filters(query, intent)

    # Semantic tags (high-level labels)
    semantic_tags: list[str] = []
    if intent == "animal_search":
        semantic_tags = ["动物", "宠物", "野生动物"]
    elif intent == "weather_search":
        semantic_tags = ["天气", "自然"]
    elif intent == "activity_search":
        semantic_tags = ["户外", "自然", "旅行"]
    elif intent == "people_search":
        semantic_tags = ["人物", "生活"]
    elif intent == "food_search":
        semantic_tags = ["美食", "生活"]
    elif intent == "location_search":
        semantic_tags = ["地点", "旅行", "风景"]

    return SearchQueryPlan(
        original_query=query,
        normalized_query=normalized_query,
        expanded_terms=expanded_terms,
        semantic_tags=semantic_tags,
        intent=intent,
        search_mode=search_mode,
        filters=filters,
    )
