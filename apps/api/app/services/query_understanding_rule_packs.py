from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

DEFAULT_BASE_PACK_ID = "lifestyle_default"
_ALLOWED_DICT_BUCKETS = ("outdoor", "weather", "animal", "people", "food", "travel", "indoor")
_PACK_DIR = Path(__file__).resolve().parent / "query_understanding_packs"


@dataclass(frozen=True)
class QueryUnderstandingRuleSet:
    base_pack_id: str
    extension_pack_ids: tuple[str, ...]
    tiered_terms: dict[str, dict[str, dict[str, Any]]]
    concept_taxonomy: list[dict[str, Any]]
    activity_phrase_overrides: frozenset[str]


@lru_cache(maxsize=32)
def build_rule_set(
    base_pack_id: str = DEFAULT_BASE_PACK_ID,
    extension_pack_ids: tuple[str, ...] = (),
) -> QueryUnderstandingRuleSet:
    base = _load_pack(base_pack_id)

    merged_terms: dict[str, dict[str, dict[str, Any]]] = {
        bucket: dict(base["tiered_terms"][bucket]) for bucket in _ALLOWED_DICT_BUCKETS
    }
    merged_taxonomy = list(base.get("concept_taxonomy") or [])
    merged_activity_overrides = set(base.get("activity_phrase_overrides") or [])

    for pack_id in extension_pack_ids:
        ext = _load_pack(pack_id)
        for bucket in _ALLOWED_DICT_BUCKETS:
            merged_terms[bucket].update(ext["tiered_terms"][bucket])
        merged_activity_overrides.update(ext.get("activity_phrase_overrides") or [])
        merged_taxonomy.extend(ext.get("concept_taxonomy") or [])

    return QueryUnderstandingRuleSet(
        base_pack_id=base_pack_id,
        extension_pack_ids=extension_pack_ids,
        tiered_terms=merged_terms,
        concept_taxonomy=merged_taxonomy,
        activity_phrase_overrides=frozenset(merged_activity_overrides),
    )


def normalise_extension_pack_ids(raw: Optional[list[Any]]) -> tuple[str, ...]:
    if not raw:
        return ()
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return tuple(values)


def _load_pack(pack_id: str) -> dict[str, Any]:
    if not pack_id:
        raise ValueError("Missing query understanding pack id")

    pack_path = _PACK_DIR / f"{pack_id}.json"
    if not pack_path.exists():
        raise ValueError(f"Unknown query understanding pack: {pack_id}")

    with pack_path.open("r", encoding="utf-8") as fp:
        raw = json.load(fp)

    if not isinstance(raw, dict):
        raise ValueError(f"Invalid rule pack format for {pack_id}")

    raw_terms = raw.get("tiered_terms")
    if not isinstance(raw_terms, dict):
        raise ValueError(f"Pack {pack_id} missing tiered_terms")

    normalized_terms: dict[str, dict[str, dict[str, Any]]] = {}
    for bucket in _ALLOWED_DICT_BUCKETS:
        bucket_raw = raw_terms.get(bucket) or {}
        if not isinstance(bucket_raw, dict):
            raise ValueError(f"Pack {pack_id} has invalid bucket: {bucket}")
        cleaned_bucket: dict[str, dict[str, Any]] = {}
        for key, value in bucket_raw.items():
            token = str(key or "").strip()
            if not token or not isinstance(value, dict):
                continue
            cleaned_bucket[token] = {
                "expanded": _normalise_str_list(value.get("expanded")),
                "support": _normalise_str_list(value.get("support")),
                "broad": _normalise_str_list(value.get("broad")),
                "negative": _normalise_str_list(value.get("negative")),
                "facets": _normalise_str_list(value.get("facets")),
                "core_facet_positive": _normalise_str_list(value.get("core_facet_positive")),
                "core_facet_negative": _normalise_str_list(value.get("core_facet_negative")),
            }
        normalized_terms[bucket] = cleaned_bucket

    taxonomy = raw.get("concept_taxonomy")
    if taxonomy is not None and not isinstance(taxonomy, list):
        raise ValueError(f"Pack {pack_id} has invalid concept_taxonomy")

    activity_overrides = raw.get("activity_phrase_overrides")
    if activity_overrides is not None and not isinstance(activity_overrides, list):
        raise ValueError(f"Pack {pack_id} has invalid activity_phrase_overrides")

    return {
        "tiered_terms": normalized_terms,
        "concept_taxonomy": list(taxonomy or []),
        "activity_phrase_overrides": _normalise_str_list(activity_overrides),
    }


def _normalise_str_list(raw: Optional[list[Any]]) -> list[str]:
    if not raw:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result
