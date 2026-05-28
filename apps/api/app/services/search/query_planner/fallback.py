"""Fallback helpers for query planner failures."""
from __future__ import annotations

from typing import Callable, Optional

from ...query_understanding_service import SearchQueryPlan


def build_fallback_plan(
    *,
    query: str,
    project_id: Optional[int],
    understander: Callable,
    concept_taxonomy: list[dict],
    rule_base_pack_id: str,
    rule_extension_pack_ids: list[str],
    planner_debug: dict,
) -> SearchQueryPlan:
    plan = understander(
        query,
        project_id=project_id,
        concept_taxonomy=concept_taxonomy,
        rule_base_pack_id=rule_base_pack_id,
        rule_extension_pack_ids=rule_extension_pack_ids,
    )
    plan.planner_debug = dict(planner_debug)
    return plan
