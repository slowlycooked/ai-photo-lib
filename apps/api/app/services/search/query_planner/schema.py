"""Pydantic schema for LLM query planner output."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    metadata_filters: PlannerMetadataFilters = Field(default_factory=PlannerMetadataFilters)
    concept_terms: list[str] = Field(default_factory=list)
    semantic_tags: list[str] = Field(default_factory=list)
    core_facets: list[str] = Field(default_factory=list)
    core_facet_evidence: PlannerCoreFacetEvidence = Field(default_factory=PlannerCoreFacetEvidence)
    query_constraints: PlannerQueryConstraints = Field(default_factory=PlannerQueryConstraints)
    confidence: float = 0.0
    fallback_reason: str = ""
