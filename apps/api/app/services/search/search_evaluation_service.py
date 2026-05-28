"""Search regression evaluation service for fixed query sets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

from .types import SearchMode


@dataclass(frozen=True)
class SearchEvaluationCase:
    name: str
    query: str
    expected_photo_ids: tuple[int, ...] = ()
    mode: SearchMode = "hybrid"
    min_total: int = 0


@dataclass(frozen=True)
class SearchEvaluationResult:
    name: str
    passed: bool
    total: int
    returned_photo_ids: tuple[int, ...]
    expected_photo_ids: tuple[int, ...]
    reason: str


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
    ) -> list[SearchEvaluationResult]:
        results: list[SearchEvaluationResult] = []
        for case in cases:
            total, items, _ = self._search_fn(
                self._db,
                case.query,
                page=1,
                page_size=page_size,
                project_id=self._project_id,
                mode=case.mode,
                debug=False,
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

            results.append(
                SearchEvaluationResult(
                    name=case.name,
                    passed=passed,
                    total=total,
                    returned_photo_ids=returned_ids,
                    expected_photo_ids=case.expected_photo_ids,
                    reason=reason,
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
