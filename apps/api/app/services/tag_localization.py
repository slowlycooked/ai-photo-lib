from __future__ import annotations

import re
import unicodedata

_TAG_ALIAS_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("夜晚", ("night", "nighttime", "夜", "夜景", "夜色")),
    ("建筑", ("architecture", "建筑物")),
    ("塔", ("tower", "塔楼")),
    ("楼", ("building", "大楼", "楼宇")),
    ("传统", ("traditional", "traditional_style", "古风")),
    ("清晰", ("clear",)),
    ("高清", ("high quality", "high_quality", "hd", "sharp")),
    ("城市", ("city", "urban")),
    ("室内", ("indoor", "inside")),
    ("户外", ("outdoor", "outside")),
    ("海边", ("beach", "seaside", "shore")),
    ("大海", ("sea", "ocean")),
    ("山", ("mountain", "hill")),
    ("森林", ("forest", "woods")),
    ("动物园", ("zoo", "animal park", "wildlife park")),
    ("船", ("boat", "ship")),
    ("划船", ("boating", "rowing", "boat ride")),
    ("开船", ("sailing",)),
    ("皮划艇", ("kayaking", "kayak")),
    ("独木舟", ("canoeing", "canoe")),
    ("徒步", ("hiking", "trekking")),
    ("露营", ("camping",)),
    ("旅行", ("travel", "trip", "tourism")),
    ("度假", ("vacation", "holiday")),
    ("人像", ("portrait",)),
    ("合影", ("group photo", "group", "group shot")),
    ("家庭", ("family",)),
    ("孩子", ("child", "children", "kid", "kids")),
    ("猫", ("cat",)),
    ("狗", ("dog",)),
    ("汽车", ("car",)),
    ("自行车", ("bicycle", "bike", "cycling")),
    ("食物", ("food",)),
    ("餐厅", ("restaurant", "dining")),
    ("日出", ("sunrise",)),
    ("日落", ("sunset",)),
    ("爸爸", ("father", "dad", "daddy")),
    ("妈妈", ("mother", "mom", "mum")),
    ("女儿", ("daughter",)),
    ("儿子", ("son",)),
    ("亲子", ("parent child", "parent-child", "parent and child")),
)

_WS_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"[_\-]+")


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).strip()
    value = _SEP_RE.sub(" ", value)
    value = _WS_RE.sub(" ", value)
    return value


def _alias_key(text: str) -> str:
    return normalize_text(text).casefold()


_ALIAS_TO_CANONICAL_ZH: dict[str, str] = {}
_CANONICAL_TO_ALIASES: dict[str, set[str]] = {}

for canonical, aliases in _TAG_ALIAS_GROUPS:
    canonical_norm = normalize_text(canonical)
    group = {canonical_norm}
    for alias in aliases:
        alias_norm = normalize_text(alias)
        if alias_norm:
            group.add(alias_norm)
    _CANONICAL_TO_ALIASES[canonical_norm] = group
    for alias in group:
        _ALIAS_TO_CANONICAL_ZH[_alias_key(alias)] = canonical_norm


def to_chinese_tag(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    return _ALIAS_TO_CANONICAL_ZH.get(_alias_key(normalized), normalized)


def expand_term_aliases(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    canonical = _ALIAS_TO_CANONICAL_ZH.get(_alias_key(normalized))
    if canonical:
        aliases = _CANONICAL_TO_ALIASES.get(canonical, {canonical})
        # Put the user-facing term first, then the Chinese canonical, then the rest.
        ordered: list[str] = []
        for candidate in (normalized, canonical, *sorted(aliases)):
            if candidate and candidate not in ordered:
                ordered.append(candidate)
        return ordered

    return [normalized]
