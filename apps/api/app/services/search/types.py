"""Shared types for the search system.

All search modules import their core dataclasses from here so that
``search_service.py`` compatibility imports keep working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

SearchMode = Literal["keyword", "vector", "hybrid"]

# ── Default weight constants ───────────────────────────────────────────────────

DEFAULT_KEYWORD_FIELD_WEIGHTS: Dict[str, float] = {
    "caption": 3.0,
    "ocr_text": 5.0,
    "scene_tags": 4.0,
    "object_tags": 4.0,
    "activity_tags": 4.0,
    "search_keywords": 4.0,
    "quality_tags": 2.0,
    "location_clues": 2.0,
    "file_name": 1.0,
}

DEFAULT_VECTOR_FIELD_WEIGHTS: Dict[str, float] = {
    "content_embedding": 0.50,
    "tag_embedding": 0.25,
    "caption_embedding": 0.20,
    "ocr_embedding": 0.05,
}

DEFAULT_OCR_VECTOR_FIELD_WEIGHTS: Dict[str, float] = {
    "content_embedding": 0.35,
    "tag_embedding": 0.15,
    "caption_embedding": 0.10,
    "ocr_embedding": 0.40,
}

# Tier multipliers for keyword scoring
EXACT_TERM_MULTIPLIER: float = 1.0
EXPANDED_TERM_MULTIPLIER: float = 0.7
BROAD_TERM_MULTIPLIER: float = 0.3


# ── Settings dataclass ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EffectiveSearchSettings:
    """Project-scoped merged search parameters.

    Sources (priority order):
      1. project_search_settings table row
      2. project_embedding_settings.search_*_vector_weight columns
      3. config.py search_* defaults
    """

    default_mode: SearchMode
    keyword_top_k: int
    vector_top_k: int
    rrf_k: int
    keyword_weight: float
    vector_weight: float
    vector_min_score: float
    keyword_field_weights: Dict[str, float]
    vector_field_weights: Dict[str, float]
    ocr_vector_field_weights: Dict[str, float]
    enable_query_understanding: bool
    enable_structured_filters: bool
    enable_semantic_tag_boost: bool


# ── Candidate / score dataclasses ─────────────────────────────────────────────

@dataclass
class VectorMatchScores:
    content_score: float = 0.0
    caption_score: float = 0.0
    tag_score: float = 0.0
    ocr_score: float = 0.0
    total_score: float = 0.0


@dataclass
class SearchCandidate:
    photo_id: int
    keyword_score: float = 0.0
    vector_score: float = 0.0
    final_score: float = 0.0
    rrf_score: float = 0.0
    matched_tags: List[str] = field(default_factory=list)
    match_source: List[str] = field(default_factory=list)
    field_scores: Dict = field(default_factory=dict)
    # Extended for debug explain
    keyword_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    keyword_explain: Dict = field(default_factory=dict)
    vector_explain: Dict = field(default_factory=dict)
