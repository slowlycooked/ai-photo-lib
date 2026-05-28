"""Modular search package.

Modules
-------
types               Shared dataclasses (EffectiveSearchSettings, SearchCandidate, …)
orchestrator        SearchOrchestrator — stage coordination
settings_resolver   SearchSettingsResolver — merges project_search_settings / config
keyword_recall      KeywordRecallService
vector_recall       VectorRecallService
fusion              FusionService (RRF merge)
result_hydrator     ResultHydrator (photo + AI data assembly)
debug               Search debug payload primitives
debug_builder       SearchDebugBuilder — orchestration-facing debug factory
facet_evidence_policy FacetEvidencePolicy — evidence and facet wrappers
fallback_policy     SearchFallbackPolicy — metadata/vector fallback handling
search_evaluation_catalog Default fixed-query regression cases
search_evaluation_service SearchEvaluationService — fixed query regression checks
app_service         Compatibility entry-point exposing search_photos()
"""
