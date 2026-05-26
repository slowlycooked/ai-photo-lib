from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..models.ai import PhotoAIAnalysis

CONCEPT_NORMALIZER_VERSION = "concept_normalizer_v1"

_ANIMAL_ENTITY_TO_CONCEPTS: dict[str, list[str]] = {
    "猫": ["动物", "宠物", "小动物"],
    "狗": ["动物", "宠物", "小动物"],
    "兔子": ["动物", "宠物", "小动物"],
    "鸟": ["动物", "小动物"],
    "马": ["动物"],
    "鹿": ["动物", "野生动物"],
    "鱼": ["动物", "水生动物"],
    "蝴蝶": ["动物", "昆虫", "小动物"],
    "昆虫": ["动物", "昆虫", "小动物"],
}

_ENTITY_ALIASES: dict[str, str] = {
    "猫": "猫",
    "小猫": "猫",
    "猫咪": "猫",
    "cat": "猫",
    "狗": "狗",
    "小狗": "狗",
    "狗狗": "狗",
    "dog": "狗",
    "兔": "兔子",
    "兔子": "兔子",
    "小兔": "兔子",
    "rabbit": "兔子",
    "鸟": "鸟",
    "小鸟": "鸟",
    "飞鸟": "鸟",
    "禽鸟": "鸟",
    "bird": "鸟",
    "马": "马",
    "骏马": "马",
    "horse": "马",
    "鹿": "鹿",
    "梅花鹿": "鹿",
    "野鹿": "鹿",
    "deer": "鹿",
    "鱼": "鱼",
    "水族": "鱼",
    "fish": "鱼",
    "蝴蝶": "蝴蝶",
    "butterfly": "蝴蝶",
    "昆虫": "昆虫",
    "insect": "昆虫",
}

_CONCEPT_ALIASES: dict[str, str] = {
    "动物": "动物",
    "animal": "动物",
    "宠物": "宠物",
    "pet": "宠物",
    "小动物": "小动物",
    "野生动物": "野生动物",
    "水生动物": "水生动物",
    "昆虫": "昆虫",
}

_WEAK_SCENE_TERMS: set[str] = {"动物园", "宠物店", "野外"}
_ANIMAL_CONCEPT_TERMS: set[str] = {
    "动物",
    "宠物",
    "小动物",
    "野生动物",
    "水生动物",
    "昆虫",
}

_PEOPLE_CONCEPT_ALIASES: dict[str, str] = {
    "人物": "人物",
    "people": "人物",
    "person": "人物",
    "单人照": "单人照",
    "人像": "人像",
    "portrait": "人像",
    "多人": "多人",
    "合照": "合照",
    "合影": "合影",
    "集体照": "集体照",
    "group photo": "合照",
    "selfie": "自拍",
    "自拍": "自拍",
    "全家福": "全家福",
}

_GROUP_PHOTO_TERMS: set[str] = {"多人", "合照", "合影", "集体照", "全家福", "多人合照", "多人合影", "group photo"}


@dataclass(frozen=True)
class NormalizedConcepts:
    semantic_entities: list[str]
    semantic_concepts: list[str]
    semantic_facets: list[str]
    concept_sources: dict[str, list[str]]


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_animal_alias(term: str) -> Optional[str]:
    text = str(term).strip().lower()
    if not text:
        return None
    return _ENTITY_ALIASES.get(text)


def _normalize_concept_alias(term: str) -> Optional[str]:
    text = str(term).strip().lower()
    if not text:
        return None
    return _CONCEPT_ALIASES.get(text)


def _extract_term_hits(source: str, term: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    text = str(term).strip()
    if not text:
        return hits

    canonical = _normalize_animal_alias(text)
    if canonical:
        hits.append((canonical, f"{source}:{text}"))

    lower_text = text.lower()
    for alias, entity in _ENTITY_ALIASES.items():
        if alias in lower_text and entity != canonical:
            hits.append((entity, f"{source}:{text}"))

    return hits


def _extract_terms_from_ai_payload(
    *,
    caption: Optional[str] = None,
    scene_tags: Optional[list[str]] = None,
    object_tags: Optional[list[str]] = None,
    activity_tags: Optional[list[str]] = None,
    search_keywords: Optional[list[str]] = None,
    location_clues: Optional[list[str]] = None,
    raw_result: Optional[dict] = None,
) -> list[tuple[str, str]]:
    terms: list[tuple[str, str]] = []

    def _push(source: str, values: object) -> None:
        for value in _as_list(values):
            terms.append((source, value))

    _push("raw_result.animals", (raw_result or {}).get("animals") if isinstance(raw_result, dict) else None)
    _push("object_tags", object_tags)
    _push("search_keywords", search_keywords)
    _push("caption", caption)

    _push("raw_result.object_tags", (raw_result or {}).get("object_tags") if isinstance(raw_result, dict) else None)
    _push("raw_result.search_keywords", (raw_result or {}).get("search_keywords") if isinstance(raw_result, dict) else None)
    _push("raw_result.caption", (raw_result or {}).get("caption") if isinstance(raw_result, dict) else None)

    _push("scene_tags", scene_tags)
    _push("activity_tags", activity_tags)
    _push("location_clues", location_clues)

    return terms


def _derive_concepts_for_entity(entity: str) -> list[str]:
    return list(_ANIMAL_ENTITY_TO_CONCEPTS.get(entity, []))


def normalize_concepts_from_payload(
    *,
    caption: Optional[str] = None,
    scene_tags: Optional[list[str]] = None,
    object_tags: Optional[list[str]] = None,
    activity_tags: Optional[list[str]] = None,
    search_keywords: Optional[list[str]] = None,
    location_clues: Optional[list[str]] = None,
    raw_result: Optional[dict] = None,
    people_count: Optional[int] = None,
) -> NormalizedConcepts:
    terms = _extract_terms_from_ai_payload(
        caption=caption,
        scene_tags=scene_tags,
        object_tags=object_tags,
        activity_tags=activity_tags,
        search_keywords=search_keywords,
        location_clues=location_clues,
        raw_result=raw_result,
    )

    entities: list[str] = []
    concepts: list[str] = []
    concept_sources: dict[str, list[str]] = {}

    weak_sources = {"scene_tags", "location_clues", "activity_tags"}

    def _add_entity(entity: str) -> None:
        if entity not in entities:
            entities.append(entity)

    def _add_concept(concept: str, source_ref: str) -> None:
        if concept not in concepts:
            concepts.append(concept)
        concept_sources.setdefault(concept, [])
        if source_ref not in concept_sources[concept]:
            concept_sources[concept].append(source_ref)

    def _coerce_people_count(value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    resolved_people_count: Optional[int] = None
    for candidate in (
        people_count,
        (raw_result or {}).get("people_count") if isinstance(raw_result, dict) else None,
        (raw_result or {}).get("face_count") if isinstance(raw_result, dict) else None,
        len((raw_result or {}).get("faces") or []) if isinstance(raw_result, dict) and isinstance((raw_result or {}).get("faces"), list) else None,
    ):
        coerced = _coerce_people_count(candidate)
        if coerced is not None:
            resolved_people_count = coerced
            break

    if resolved_people_count is not None and resolved_people_count >= 1:
        _add_concept("人物", f"people_count:{resolved_people_count}")
    if resolved_people_count == 1:
        _add_concept("单人照", f"people_count:{resolved_people_count}")
        _add_concept("人像", f"people_count:{resolved_people_count}")
    if resolved_people_count is not None and resolved_people_count >= 2:
        _add_concept("多人", f"people_count:{resolved_people_count}")
        _add_concept("合照", f"people_count:{resolved_people_count}")
        _add_concept("合影", f"people_count:{resolved_people_count}")
    if resolved_people_count is not None and resolved_people_count >= 3:
        _add_concept("集体照", f"people_count:{resolved_people_count}")

    for source, term in terms:
        term_text = str(term).strip()
        if not term_text:
            continue

        if source in weak_sources and term_text in _WEAK_SCENE_TERMS:
            continue

        for entity, source_ref in _extract_term_hits(source, term_text):
            _add_entity(entity)
            for concept in _derive_concepts_for_entity(entity):
                _add_concept(concept, source_ref)

        concept_alias = _normalize_concept_alias(term_text)
        if concept_alias and concept_alias != "动物":
            _add_concept(concept_alias, f"{source}:{term_text}")
        elif concept_alias == "动物" and source not in weak_sources:
            _add_concept(concept_alias, f"{source}:{term_text}")

        lower_text = term_text.lower()
        for alias, people_concept in _PEOPLE_CONCEPT_ALIASES.items():
            if alias in lower_text:
                _add_concept(people_concept, f"{source}:{term_text}")

    if any(term in (caption or "").lower() for term in _GROUP_PHOTO_TERMS):
        _add_concept("多人", f"caption:{caption}")
        _add_concept("合照", f"caption:{caption}")
        _add_concept("合影", f"caption:{caption}")

    entities = _dedupe_preserve_order(entities)
    concepts = _dedupe_preserve_order(concepts)

    facets: list[str] = []
    has_animal_semantics = bool(entities) or any(concept in _ANIMAL_CONCEPT_TERMS for concept in concepts)
    has_people_semantics = any(concept in {"人物", "单人照", "人像", "多人", "合照", "合影", "集体照", "自拍", "全家福"} for concept in concepts)
    has_group_photo_semantics = any(concept in {"多人", "合照", "合影", "集体照", "全家福"} for concept in concepts)

    if has_animal_semantics:
        facets.append("object")
    if has_animal_semantics:
        facets.append("animal")
    if has_people_semantics:
        facets.append("people")
    if has_group_photo_semantics:
        facets.append("group_photo")

    return NormalizedConcepts(
        semantic_entities=entities,
        semantic_concepts=concepts,
        semantic_facets=_dedupe_preserve_order(facets),
        concept_sources={k: _dedupe_preserve_order(v) for k, v in concept_sources.items()},
    )


def normalize_photo_ai_analysis(ai_analysis: PhotoAIAnalysis) -> NormalizedConcepts:
    return normalize_concepts_from_payload(
        caption=ai_analysis.caption,
        scene_tags=ai_analysis.scene_tags,
        object_tags=ai_analysis.object_tags,
        activity_tags=ai_analysis.activity_tags,
        search_keywords=ai_analysis.search_keywords,
        location_clues=ai_analysis.location_clues,
        raw_result=ai_analysis.raw_result if isinstance(ai_analysis.raw_result, dict) else None,
        people_count=ai_analysis.people_count,
    )


def attach_semantic_concepts_to_raw_result(
    raw_result: object,
    normalized: NormalizedConcepts,
) -> dict:
    base: dict
    if raw_result is None:
        base = {}
    elif isinstance(raw_result, dict):
        base = dict(raw_result)
    else:
        base = {"_legacy_raw_result": str(raw_result)}

    base["semantic"] = {
        "entities": _dedupe_preserve_order(normalized.semantic_entities),
        "concepts": _dedupe_preserve_order(normalized.semantic_concepts),
        "facets": _dedupe_preserve_order(normalized.semantic_facets),
        "sources": {k: _dedupe_preserve_order(v) for k, v in normalized.concept_sources.items()},
        "version": CONCEPT_NORMALIZER_VERSION,
    }
    return base
