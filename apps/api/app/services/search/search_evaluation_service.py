"""Search regression evaluation service for fixed query sets."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from .types import SearchMode


@dataclass(frozen=True)
class SearchEvaluationCase:
    name: str
    query: str
    expected_photo_ids: tuple[int, ...] = ()
    mode: SearchMode = "hybrid"
    min_total: int = 0
    expected_plan: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchEvaluationResult:
    name: str
    passed: bool
    total: int
    returned_photo_ids: tuple[int, ...]
    expected_photo_ids: tuple[int, ...]
    reason: str
    debug_payload: Optional[dict] = None


class SearchEvaluationService:
    """Runs deterministic query checks against project-scoped search."""

    def __init__(
        self,
        db: Session,
        project_id: int,
        *,
        search_fn: Optional[Callable[..., tuple[int, list, Optional[dict]]]] = None,
    ) -> None:
        self._db = db
        self._project_id = project_id
        if search_fn is None:
            from .app_service import search_photos

            self._search_fn = search_photos
        else:
            self._search_fn = search_fn

    def evaluate_cases(
        self,
        cases: list[SearchEvaluationCase],
        *,
        page_size: int = 20,
        debug: bool = False,
    ) -> list[SearchEvaluationResult]:
        results: list[SearchEvaluationResult] = []
        for case in cases:
            total, items, debug_payload = self._search_fn(
                self._db,
                case.query,
                page=1,
                page_size=page_size,
                project_id=self._project_id,
                mode=case.mode,
                debug=debug,
            )
            returned_ids = tuple(
                int(item["photo_id"])
                for item in items
                if isinstance(item, dict) and item.get("photo_id") is not None
            )

            missing = [photo_id for photo_id in case.expected_photo_ids if photo_id not in returned_ids]
            passed = (total >= case.min_total) and (not missing)
            reason = "ok"
            if total < case.min_total:
                reason = f"total {total} < min_total {case.min_total}"
            elif missing:
                reason = f"missing expected ids: {missing}"
            plan_failures = _evaluate_expected_plan(
                debug_payload if debug else None,
                case.expected_plan,
            )
            if plan_failures:
                passed = False
                reason = "; ".join(plan_failures)

            results.append(
                SearchEvaluationResult(
                    name=case.name,
                    passed=passed,
                    total=total,
                    returned_photo_ids=returned_ids,
                    expected_photo_ids=case.expected_photo_ids,
                    reason=reason,
                    debug_payload=debug_payload if debug else None,
                )
            )
        return results

    def evaluate_default_cases(
        self,
        *,
        page_size: int = 20,
    ) -> list[SearchEvaluationResult]:
        from .search_evaluation_catalog import SEARCH_EVALUATION_BASELINES

        return self.evaluate_cases(list(SEARCH_EVALUATION_BASELINES), page_size=page_size)

    def evaluate_planner_debug_cases(
        self,
        *,
        page_size: int = 20,
    ) -> list[SearchEvaluationResult]:
        from .search_evaluation_catalog import SEARCH_PLANNER_DEBUG_EVALUATION_SET

        return self.evaluate_cases(
            list(SEARCH_PLANNER_DEBUG_EVALUATION_SET),
            page_size=page_size,
            debug=True,
        )


def _is_present(value: Any) -> bool:
    return value not in (None, "", [], {}, False)


def _contains_all(actual: Any, expected_values: list[Any]) -> bool:
    if not isinstance(actual, list):
        return False
    actual_text = [str(item) for item in actual]
    return all(any(str(expected) in item for item in actual_text) for expected in expected_values)


def _evaluate_expected_plan(
    debug_payload: Optional[dict],
    expected_plan: dict[str, Any],
) -> list[str]:
    if not expected_plan:
        return []
    if not debug_payload:
        return ["missing debug payload for expected plan checks"]

    failures: list[str] = []
    planner_debug = debug_payload.get("query_planner") or (debug_payload.get("query_plan") or {}).get("query_planner") or {}
    expected_route = expected_plan.get("planner_route")
    if expected_route and planner_debug.get("planner_route") != expected_route:
        failures.append(
            f"planner_route {planner_debug.get('planner_route')!r} != {expected_route!r}"
        )

    expected_intent = expected_plan.get("intent")
    if expected_intent and debug_payload.get("intent") != expected_intent:
        failures.append(f"intent {debug_payload.get('intent')!r} != {expected_intent!r}")

    expected_semantic_query = expected_plan.get("semantic_query")
    semantic_query_text = str(debug_payload.get("semantic_query_text") or "")
    if expected_semantic_query == "empty" and semantic_query_text:
        failures.append("semantic_query_text expected empty")
    elif expected_semantic_query == "non_empty" and not semantic_query_text:
        failures.append("semantic_query_text expected non-empty")

    metadata = debug_payload.get("metadata_filters") or {}
    for key, expected_value in (expected_plan.get("metadata") or {}).items():
        if key.endswith("_contains"):
            metadata_key = key[: -len("_contains")]
            if not _contains_all(metadata.get(metadata_key), list(expected_value or [])):
                failures.append(f"metadata.{metadata_key} missing {list(expected_value or [])!r}")
            continue
        if key.endswith("_present"):
            metadata_key = key[: -len("_present")]
            if bool(expected_value) and not _is_present(metadata.get(metadata_key)):
                failures.append(f"metadata.{metadata_key} expected present")
            continue
        if metadata.get(key) != expected_value:
            failures.append(f"metadata.{key} {metadata.get(key)!r} != {expected_value!r}")

    term_groups = debug_payload.get("term_groups") or {}
    for group, expected_terms in (expected_plan.get("term_groups_contains") or {}).items():
        if not _contains_all(term_groups.get(group), list(expected_terms or [])):
            failures.append(f"term_groups.{group} missing {list(expected_terms or [])!r}")

    return failures
