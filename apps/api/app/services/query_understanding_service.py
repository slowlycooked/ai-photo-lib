"""Rule-based query understanding service.

Three-tier term model
---------------------
exact_terms     Words that appear directly in the user's query.
expanded_terms  Close synonyms / direct variants (score × 0.7).
broad_terms     Generic category terms (score × 0.3).

normalized_query joins all three tiers for embedding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional, TypedDict


# ── Tiered expansion dictionaries ─────────────────────────────────────────────

class _TieredTerms(TypedDict):
    expanded: list[str]
    broad: list[str]


_OUTDOOR_TERMS_TIERED: dict[str, _TieredTerms] = {
    "爬山": {"expanded": ["登山", "徒步", "山路", "山顶", "山峰"], "broad": ["户外", "背包", "登山杖"]},
    "登山": {"expanded": ["爬山", "徒步", "山路", "山顶", "山峰"], "broad": ["户外", "背包"]},
    "徒步": {"expanded": ["登山", "山路", "步道"], "broad": ["户外", "背包"]},
    "户外": {"expanded": ["自然", "山地", "步道", "草地", "树林"], "broad": []},
    "山顶": {"expanded": ["山峰", "登山", "爬山"], "broad": ["远眺"]},
    "山峰": {"expanded": ["山顶", "登山", "爬山"], "broad": ["壮观"]},
    "步道": {"expanded": ["徒步", "山路", "登山"], "broad": ["户外"]},
    "远足": {"expanded": ["徒步", "户外", "山路"], "broad": ["背包"]},
    "hiking": {"expanded": ["徒步", "登山"], "broad": ["户外", "背包", "山路"]},
    "山": {"expanded": ["山地", "山峰", "山顶"], "broad": ["户外", "自然"]},
}

_WEATHER_TERMS_TIERED: dict[str, _TieredTerms] = {
    "下雨": {"expanded": ["雨天", "雨伞", "雨衣", "雨滴"], "broad": ["积水", "湿地面", "阴天"]},
    "下雨天": {"expanded": ["下雨", "雨天", "雨伞", "雨滴"], "broad": ["积水", "湿地面", "阴天"]},
    "雨天": {"expanded": ["下雨", "雨伞", "雨滴"], "broad": ["积水", "阴天"]},
    "下雪": {"expanded": ["雪天", "雪地", "雪花"], "broad": ["积雪", "寒冷"]},
    "雪天": {"expanded": ["下雪", "雪地", "积雪"], "broad": ["寒冷"]},
    "晴天": {"expanded": ["阳光", "蓝天", "白云"], "broad": ["户外"]},
    "出太阳": {"expanded": ["晴天", "阳光", "蓝天"], "broad": ["白云", "户外", "日照"]},
    "太阳": {"expanded": ["晴天", "阳光", "蓝天"], "broad": ["白云", "户外", "日照"]},
    "阳光": {"expanded": ["晴天", "蓝天", "白云"], "broad": ["户外", "日照"]},
    "晴朗": {"expanded": ["晴天", "阳光", "蓝天"], "broad": ["白云", "户外"]},
    "阴天": {"expanded": ["多云", "乌云"], "broad": ["灰色天空"]},
    "大风": {"expanded": ["风大", "风吹"], "broad": ["户外", "飞扬"]},
    "雨伞": {"expanded": ["下雨", "雨天"], "broad": ["防雨"]},
    "rain": {"expanded": ["下雨", "雨天", "雨伞", "雨滴"], "broad": ["积水", "阴天"]},
    "snow": {"expanded": ["下雪", "雪天", "雪地"], "broad": ["积雪"]},
    "sunny": {"expanded": ["晴天", "阳光", "蓝天", "白云"], "broad": ["户外"]},
    "sunshine": {"expanded": ["阳光", "晴天", "蓝天", "白云"], "broad": ["户外"]},
}

_ANIMAL_TERMS_TIERED: dict[str, _TieredTerms] = {
    "猫": {"expanded": ["小猫", "猫咪"], "broad": ["宠物", "动物"]},
    "狗": {"expanded": ["小狗", "狗狗"], "broad": ["宠物", "动物"]},
    "鸟": {"expanded": ["小鸟", "飞鸟", "禽鸟"], "broad": ["动物"]},
    "动物": {"expanded": ["猫", "狗", "鸟", "马", "鹿"], "broad": ["宠物", "野生动物", "动物园"]},
    "猫狗": {"expanded": ["猫", "狗"], "broad": ["宠物", "动物"]},
    "宠物": {"expanded": ["猫", "狗"], "broad": ["动物"]},
    "野生动物": {"expanded": ["动物", "野外"], "broad": ["自然", "户外"]},
    "动物园": {"expanded": ["动物", "野生动物"], "broad": []},
    "马": {"expanded": ["骏马", "骑马"], "broad": ["动物"]},
    "鹿": {"expanded": ["梅花鹿", "野鹿"], "broad": ["动物"]},
    "兔子": {"expanded": ["小兔"], "broad": ["宠物", "动物"]},
    "鱼": {"expanded": ["水族"], "broad": ["海洋", "动物"]},
    "蝴蝶": {"expanded": ["昆虫"], "broad": ["花园", "动物"]},
    "animal": {"expanded": ["动物", "猫", "狗", "鸟"], "broad": ["宠物", "野生动物"]},
    "cat": {"expanded": ["猫", "小猫"], "broad": ["宠物", "动物"]},
    "dog": {"expanded": ["狗", "小狗"], "broad": ["宠物", "动物"]},
    "bird": {"expanded": ["鸟", "小鸟", "飞鸟"], "broad": ["动物"]},
}

_PEOPLE_TERMS_TIERED: dict[str, _TieredTerms] = {
    "孩子": {"expanded": ["小孩", "儿童", "玩耍"], "broad": ["童年", "幼儿"]},
    "儿童": {"expanded": ["孩子", "小孩", "玩耍"], "broad": []},
    "小孩": {"expanded": ["孩子", "儿童", "玩耍"], "broad": []},
    "婴儿": {"expanded": ["宝宝", "小孩"], "broad": ["孩子"]},
    "老人": {"expanded": ["长辈", "老年人"], "broad": []},
    "全家福": {"expanded": ["家庭", "合影", "多人"], "broad": []},
    "自拍": {"expanded": ["selfie", "单人"], "broad": []},
    "合影": {"expanded": ["集体照", "合照", "多人"], "broad": []},
}

_FOOD_TERMS_TIERED: dict[str, _TieredTerms] = {
    "食物": {"expanded": ["美食", "饭菜", "料理"], "broad": ["餐厅"]},
    "美食": {"expanded": ["食物", "料理", "饭菜"], "broad": []},
    "餐厅": {"expanded": ["饭馆", "美食", "食物"], "broad": []},
    "咖啡": {"expanded": ["coffee", "咖啡馆"], "broad": ["饮品"]},
    "甜点": {"expanded": ["蛋糕", "甜食"], "broad": ["美食"]},
}

_TRAVEL_TERMS_TIERED: dict[str, _TieredTerms] = {
    "旅行": {"expanded": ["旅游", "出行"], "broad": ["风景", "景点"]},
    "旅游": {"expanded": ["旅行", "出行"], "broad": ["风景", "景点"]},
    "海边": {"expanded": ["海滩", "海岸", "海浪", "大海", "沙滩"], "broad": []},
    "沙滩": {"expanded": ["海边", "海滩", "海浪"], "broad": ["大海"]},
    "大海": {"expanded": ["海洋", "海边", "海浪"], "broad": ["海景"]},
    "海洋": {"expanded": ["大海", "海边", "海浪"], "broad": []},
    "城市": {"expanded": ["街道", "建筑", "都市"], "broad": ["夜景"]},
    "建筑": {"expanded": ["楼房", "高楼", "城市"], "broad": ["结构"]},
    "风景": {"expanded": ["自然", "景色"], "broad": ["户外"]},
    "日落": {"expanded": ["黄昏", "夕阳", "晚霞"], "broad": ["天空"]},
    "日出": {"expanded": ["清晨", "朝霞", "晨光"], "broad": ["天空"]},
    "夜景": {"expanded": ["夜晚", "灯光", "夜色"], "broad": ["城市"]},
    "sunset": {"expanded": ["日落", "黄昏", "夕阳", "晚霞"], "broad": []},
    "sunrise": {"expanded": ["日出", "清晨", "朝霞"], "broad": []},
}

_INDOOR_TERMS_TIERED: dict[str, _TieredTerms] = {
    "室内": {"expanded": ["家", "家庭", "客厅", "卧室"], "broad": []},
    "家": {"expanded": ["室内", "家庭", "生活"], "broad": []},
    "客厅": {"expanded": ["沙发", "室内"], "broad": ["家"]},
    "卧室": {"expanded": ["床", "室内"], "broad": ["家"]},
    "厨房": {"expanded": ["烹饪", "室内"], "broad": ["家"]},
    "图书馆": {"expanded": ["书架", "阅读"], "broad": ["室内"]},
    "博物馆": {"expanded": ["展览", "展品"], "broad": ["室内"]},
}

_OUTDOOR_KEYS = set(_OUTDOOR_TERMS_TIERED.keys())
_WEATHER_KEYS = set(_WEATHER_TERMS_TIERED.keys())
_ANIMAL_KEYS = set(_ANIMAL_TERMS_TIERED.keys())
_PEOPLE_KEYS = set(_PEOPLE_TERMS_TIERED.keys())
_FOOD_KEYS = set(_FOOD_TERMS_TIERED.keys())
_TRAVEL_KEYS = set(_TRAVEL_TERMS_TIERED.keys())
_INDOOR_KEYS = set(_INDOOR_TERMS_TIERED.keys())

_ALL_TIERED_DICTS: tuple = (
    _OUTDOOR_TERMS_TIERED,
    _WEATHER_TERMS_TIERED,
    _ANIMAL_TERMS_TIERED,
    _PEOPLE_TERMS_TIERED,
    _FOOD_TERMS_TIERED,
    _TRAVEL_TERMS_TIERED,
    _INDOOR_TERMS_TIERED,
)


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

    exact_terms     Words taken directly from the user's query.
    expanded_terms  Close synonyms / direct variants (scored × 0.7).
    broad_terms     Generic category terms (scored × 0.3).

    ``all_terms`` is a convenience property returning the union of all three
    tiers — use it for SQL ILIKE filter construction.
    """

    original_query: str
    normalized_query: str
    exact_terms: list[str] = field(default_factory=list)
    expanded_terms: list[str] = field(default_factory=list)
    broad_terms: list[str] = field(default_factory=list)
    semantic_tags: list[str] = field(default_factory=list)
    intent: str = "semantic_photo_search"
    search_mode: Literal["keyword", "vector", "hybrid"] = "hybrid"
    filters: dict = field(default_factory=dict)
    recommended_profile: str = "default_semantic"

    @property
    def all_terms(self) -> list[str]:
        """Union of all three tiers (deduplicated, order-preserving)."""
        seen: set[str] = set()
        result: list[str] = []
        for term in self.exact_terms + self.expanded_terms + self.broad_terms:
            tl = term.lower()
            if tl not in seen:
                seen.add(tl)
                result.append(term)
        return result


# ── Public entry point ────────────────────────────────────────────────────────

def understand_query(
    query: str,
    project_id: Optional[int] = None,
) -> SearchQueryPlan:
    """Analyse a user search query and return a structured plan (rule engine)."""
    query = query.strip()
    if not query:
        return SearchQueryPlan(original_query=query, normalized_query=query)

    search_mode: Literal["keyword", "vector", "hybrid"] = (
        "keyword" if _is_ocr_intent(query) else "hybrid"
    )
    intent = _classify_intent(query)
    profile = _recommended_profile(intent)
    q_lower = query.lower()

    # Exact terms: words from the original query
    exact_terms: list[str] = [w for w in query.split() if w]
    exact_lower: set[str] = {t.lower() for t in exact_terms}

    # Expanded / broad terms from tiered dicts
    expanded_set: set[str] = set()
    broad_set: set[str] = set()

    for tiered_dict in _ALL_TIERED_DICTS:
        for key, tiers in tiered_dict.items():
            if key in q_lower:
                for t in tiers["expanded"]:
                    if t.lower() not in exact_lower:
                        expanded_set.add(t)
                for t in tiers["broad"]:
                    tl = t.lower()
                    if tl not in exact_lower and t not in expanded_set:
                        broad_set.add(t)

    expanded_terms = sorted(t for t in expanded_set)
    broad_terms = sorted(t for t in broad_set if t not in expanded_set)

    # Normalised query = all terms joined (for vector embedding)
    all_for_norm: list[str] = exact_terms + expanded_terms + broad_terms
    seen_n: set[str] = set()
    deduped: list[str] = []
    for t in all_for_norm:
        if t.lower() not in seen_n:
            seen_n.add(t.lower())
            deduped.append(t)
    normalized_query = " ".join(deduped) if deduped else query

    semantic_tags: list[str] = {
        "animal_search": ["动物", "宠物", "野生动物"],
        "weather_search": ["天气", "自然"],
        "activity_search": ["户外", "自然", "旅行"],
        "people_search": ["人物", "生活"],
        "food_search": ["美食", "生活"],
        "location_search": ["地点", "旅行", "风景"],
    }.get(intent, [])

    filters = _infer_filters(query, intent)

    return SearchQueryPlan(
        original_query=query,
        normalized_query=normalized_query,
        exact_terms=exact_terms,
        expanded_terms=expanded_terms,
        broad_terms=broad_terms,
        semantic_tags=semantic_tags,
        intent=intent,
        search_mode=search_mode,
        filters=filters,
        recommended_profile=profile,
    )
