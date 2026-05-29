"""Shared types for the search system.

All search modules import their core dataclasses from here so that
``search_service.py`` compatibility imports keep working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from ...config import settings as global_settings

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
SUPPORT_TERM_MULTIPLIER: float = 0.5   # context-clue tier (between strong and weak)
BROAD_TERM_MULTIPLIER: float = 0.3

# Evidence level numeric scores (used in evidence-adjusted final scoring)
EVIDENCE_SCORE_MAP: Dict[str, float] = {
    "A": 1.0,
    "B": 0.7,
    "C": 0.45,
    "D": 0.15,
    "E": -0.5,
    "F": -1.0,
}

# Ordered from strongest (index 0) to weakest (index 5)
EVIDENCE_LEVEL_ORDER: List[str] = ["A", "B", "C", "D", "E", "F"]


def evidence_level_passes(level: str, min_level: str) -> bool:
    """Return True if *level* is at least as strong as *min_level*.

    e.g. evidence_level_passes("B", "C") → True  (B stronger than C)
         evidence_level_passes("D", "C") → False (D weaker than C)
    """
    try:
        return EVIDENCE_LEVEL_ORDER.index(level) <= EVIDENCE_LEVEL_ORDER.index(min_level)
    except ValueError:
        return False


# ── Settings dataclass ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EffectiveSearchSettings:
    """Project-scoped merged search parameters.

    Sources (priority order):
      1. project_search_settings.search_quality_settings JSONB (highest)
      2. project_search_settings table row scalar columns
      3. project_embedding_settings.search_*_vector_weight columns
      4. config.py search_* defaults (lowest)
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

    # ── Evidence quality settings (from search_quality_settings JSONB) ────────
    # Vector score required to show a vector-only candidate (no keyword evidence)
    vector_strict_score: float = 0.42
    # Minimum evidence level to display a result: "A"/"B"/"C"/"D"
    min_display_evidence_level: str = "C"
    # Master switch: enable evidence-based filtering
    enable_evidence_filter: bool = True
    # Apply negative_term penalties to final score
    enable_negative_penalty: bool = True
    # Scaling factor for evidence_score component added to final_score
    evidence_weight: float = 0.02
    # Additional penalty subtracted from final_score per negative-term hit
    negative_term_penalty: float = 0.01
    # Require AI-tag evidence for core facet queries (e.g. night queries must have night tags)
    require_core_facet_match: bool = False
    # Allow high-confidence vector-only matches to pass core facet gate
    allow_vector_only_for_facet_query: bool = True
    # Profile-aware vector-only controls for entity/object-heavy intents.
    entity_object_vector_only_min_score: float = 0.62
    entity_object_tag_min_score: float = 0.62
    entity_object_caption_min_score: float = 0.58
    animal_search_min_display_evidence_level: str = "B"
    # Project-level concept taxonomy used by query understanding / concept recall.
    concept_taxonomy: List[Dict] = field(default_factory=list)
    # Rule-pack selection for query understanding dictionaries/synonyms.
    query_understanding_base_pack: str = "lifestyle_default"
    query_understanding_extension_packs: List[str] = field(default_factory=list)
    # LLM query planner controls (configured via search_quality_settings JSONB).
    query_planner_enabled: bool = True
    query_planner_provider: str = "llama-server"
    query_planner_endpoint_url: str = global_settings.query_planner_base_url
    query_planner_api_key: str = ""
    query_planner_model_name: str = global_settings.query_planner_alias
    query_planner_temperature: float = 0.0
    query_planner_top_p: float = 0.1
    query_planner_max_tokens: int = 220
    query_planner_timeout_seconds: int = 20
    query_planner_json_parse_strategy: str = "strict_json_then_extract"
    query_planner_planner_version: str = "llm_query_planner_v1"
    query_planner_prompt_template: str = ""
    query_planner_system_prompt: str = ""
    query_planner_fallback_mode: str = "rule_fallback"


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
    people_score: float = 0.0
    final_score: float = 0.0
    rrf_score: float = 0.0
    matched_tags: List[str] = field(default_factory=list)
    match_source: List[str] = field(default_factory=list)
    field_scores: Dict = field(default_factory=dict)
    # Extended for debug explain
    keyword_rank: Optional[int] = None
    vector_rank: Optional[int] = None
    people_rank: Optional[int] = None
    keyword_explain: Dict = field(default_factory=dict)
    vector_explain: Dict = field(default_factory=dict)
    people_explain: Dict = field(default_factory=dict)
    # Tier-level evidence tracking
    # hit_tiers: set of tiers that produced keyword hits
    #   {"exact", "strong", "support", "weak", "negative"}
    hit_tiers: set = field(default_factory=set)
    # term_level_hits: {"exact": [...], "strong": [...], "support": [...], "weak": [...], "negative": [...]}
    term_level_hits: Dict = field(default_factory=dict)
    # evidence_level: "A"|"B"|"C"|"D"|"E"|"F" (computed post-fusion)
    evidence_level: Optional[str] = None
    # Why a candidate was filtered (for debug)
    filter_reason: Optional[str] = None
    # Score breakdown for debug explain
    score_breakdown: Dict = field(default_factory=dict)
    # Negative-term hits (terms from negative tier that matched)
    negative_hits: List[str] = field(default_factory=list)
    # Core facet check result (True = passed, False = filtered, None = not checked)
    core_facet_passed: Optional[bool] = None
