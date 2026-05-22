"""Modular search package.

Modules
-------
types               Shared dataclasses (EffectiveSearchSettings, SearchCandidate, …)
settings_resolver   SearchSettingsResolver — merges project_search_settings / config
keyword_recall      KeywordRecallService
vector_recall       VectorRecallService
fusion              FusionService (RRF merge)
result_hydrator     ResultHydrator (photo + AI data assembly)
debug               SearchDebugBuilder (debug payload + per-result explain)
app_service         SearchAppService — the single public orchestration entry-point
"""
