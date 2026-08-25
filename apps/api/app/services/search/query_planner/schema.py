"""Pydantic schema for LLM query planner output."""
from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _coerce_empty_list_to_none(cls: Any, data: Any) -> Any:
    """Replace empty list values with None for Optional scalar fields.

    LLMs sometimes output [] instead of null for nullable str/int/bool fields.
    Only coerces fields whose declared annotation is NOT a list type.
    """
    if not isinstance(data, dict):
        return data
    result = dict(data)
    for field_name, field_info in cls.model_fields.items():
        val = result.get(field_name)
        if isinstance(val, list) and len(val) == 0:
            ann = field_info.annotation
            origin = getattr(ann, "__origin__", None)
            # Keep as empty list only if the field is itself a list type
            if origin is not list:
                result[field_name] = None
    return result


_MONTH_TOKEN_RE = re.compile(r"\d{1,2}")


def _coerce_month_value(value: Any) -> Optional[int]:
    """Normalize model month output into Optional[int] in range 1..12.

    Small/quantized LLMs sometimes emit month as range/list-like strings
    such as "1-3" or "1/2/3". We keep the first valid month token.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 12 else None
    if isinstance(value, float):
        month = int(value)
        return month if 1 <= month <= 12 else None
    if isinstance(value, list):
        if not value:
            return None
        return _coerce_month_value(value[0])

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        month = int(text)
        return month if 1 <= month <= 12 else None

    for token in _MONTH_TOKEN_RE.findall(text):
        month = int(token)
        if 1 <= month <= 12:
            return month
    return None


class PlannerTerms(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exact: list[str] = Field(default_factory=list)
    expanded: list[str] = Field(default_factory=list)
    support: list[str] = Field(default_factory=list)
    broad: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class PlannerFacets(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object: list[str] = Field(default_factory=list)
    scene: list[str] = Field(default_factory=list)
    activity: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    weather: list[str] = Field(default_factory=list)
    time: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)


class PlannerFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    people_count_min: Optional[int] = None
    people_count_max: Optional[int] = None
    has_people: Optional[bool] = None
    has_animals: Optional[bool] = None
    indoor_outdoor: Optional[str] = None
    weather: Optional[str] = None
    time_of_day: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_lists(cls, data: Any) -> Any:
        return _coerce_empty_list_to_none(cls, data)


PlannerFilterValue = Union[str, int, float, bool, list[str], list[int]]


class PlannerFilterClause(BaseModel):
    """Validated dynamic filter emitted by the query planner.

    Fields and operators are intentionally allow-listed. The model describes
    intent only; it can never emit executable SQL or arbitrary column names.
    """

    model_config = ConfigDict(extra="ignore")

    field: Literal[
        "people_count",
        "taken_at",
        "created_at",
        "camera_make",
        "camera_model",
        "iso",
        "has_gps",
    ]
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "contains", "in"]
    value: PlannerFilterValue

    @model_validator(mode="after")
    def _validate_field_operator(self) -> "PlannerFilterClause":
        allowed_by_field = {
            "people_count": {"eq", "ne", "gt", "gte", "lt", "lte", "in"},
            "iso": {"eq", "ne", "gt", "gte", "lt", "lte", "in"},
            "taken_at": {"eq", "ne", "gt", "gte", "lt", "lte"},
            "created_at": {"eq", "ne", "gt", "gte", "lt", "lte"},
            "camera_make": {"eq", "ne", "contains", "in"},
            "camera_model": {"eq", "ne", "contains", "in"},
            "has_gps": {"eq", "ne"},
        }
        if self.operator not in allowed_by_field[self.field]:
            raise ValueError(f"operator {self.operator!r} is not valid for field {self.field!r}")
        if self.field == "has_gps" and not isinstance(self.value, bool):
            raise ValueError("has_gps requires a boolean value")
        if self.operator == "in" and not isinstance(self.value, list):
            raise ValueError("operator 'in' requires a list value")
        if self.field in {"people_count", "iso"}:
            values = self.value if isinstance(self.value, list) else [self.value]
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
                raise ValueError(f"field {self.field!r} requires numeric values")
        if self.field in {"taken_at", "created_at"} and not isinstance(self.value, str):
            raise ValueError(f"field {self.field!r} requires an ISO datetime string")
        if self.field in {"camera_make", "camera_model"}:
            values = self.value if isinstance(self.value, list) else [self.value]
            if any(not isinstance(value, str) for value in values):
                raise ValueError(f"field {self.field!r} requires string values")
        return self


class PlannerSortSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    field: Literal["relevance", "taken_at", "created_at"] = "relevance"
    order: Literal["asc", "desc"] = "desc"


class PlannerMetadataFilters(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: Optional[int] = None
    month: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    season: Optional[str] = None
    has_gps: Optional[bool] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    iso_min: Optional[int] = None
    iso_max: Optional[int] = None
    place_terms: list[str] = Field(default_factory=list)
    metadata_only: bool = False
    matched_metadata_terms: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_lists(cls, data: Any) -> Any:
        normalized = _coerce_empty_list_to_none(cls, data)
        if not isinstance(normalized, dict):
            return normalized
        result = dict(normalized)
        if "month" in result:
            result["month"] = _coerce_month_value(result.get("month"))
        return result


class PlannerCoreFacetEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    positive_terms: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)


class PlannerQueryConstraints(BaseModel):
    model_config = ConfigDict(extra="ignore")

    requires_visual_evidence: bool = True
    allow_weak_only_match: bool = False
    min_evidence_level: str = "C"
    query_core_facets: list[str] = Field(default_factory=list)


class LLMQueryPlannerOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    intent: str = "semantic_photo_search"
    search_mode: str = "hybrid"
    normalized_query: str = ""
    semantic_query_text: str = ""
    terms: PlannerTerms = Field(default_factory=PlannerTerms)
    facets: PlannerFacets = Field(default_factory=PlannerFacets)
    filters: PlannerFilters = Field(default_factory=PlannerFilters)
    filter_clauses: list[PlannerFilterClause] = Field(default_factory=list)
    sort: list[PlannerSortSpec] = Field(default_factory=list)
    metadata_filters: PlannerMetadataFilters = Field(default_factory=PlannerMetadataFilters)
    concept_terms: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    core_facets: list[str] = Field(default_factory=list)
    core_facet_evidence: PlannerCoreFacetEvidence = Field(default_factory=PlannerCoreFacetEvidence)
    query_constraints: PlannerQueryConstraints = Field(default_factory=PlannerQueryConstraints)
    confidence: float = 0.0
    fallback_reason: str = ""
