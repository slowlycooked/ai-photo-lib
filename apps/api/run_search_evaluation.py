"""Run read-only fixed-query search evaluation for a project.

Usage (from apps/api directory, with venv active):
    python run_search_evaluation.py --project-id 1 [--suite default|planner-debug] [--page-size 20] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

# Allow running from apps/api dir
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal
from app.services.search.search_evaluation_service import (
    SearchEvaluationResult,
    SearchEvaluationService,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", type=int, required=True, help="Run evaluation for one project")
    parser.add_argument(
        "--suite",
        choices=("default", "planner-debug"),
        default="default",
        help="Evaluation suite to run",
    )
    parser.add_argument("--page-size", type=int, default=20, help="Page size for each query evaluation")
    parser.add_argument("--json", action="store_true", help="Print JSON output instead of text")
    return parser


def _serialize_results(
    project_id: int,
    page_size: int,
    results: Sequence[SearchEvaluationResult],
    *,
    suite: str = "default",
) -> dict:
    return {
        "project_id": project_id,
        "suite": suite,
        "page_size": page_size,
        "total_cases": len(results),
        "passed_cases": sum(1 for item in results if item.passed),
        "failed_cases": sum(1 for item in results if not item.passed),
        "results": [
            {
                "name": item.name,
                "passed": item.passed,
                "total": item.total,
                "returned_photo_ids": list(item.returned_photo_ids),
                "expected_photo_ids": list(item.expected_photo_ids),
                "reason": item.reason,
                "debug": item.debug_payload,
            }
            for item in results
        ],
    }


def _format_text_report(
    project_id: int,
    page_size: int,
    results: Sequence[SearchEvaluationResult],
    *,
    suite: str = "default",
) -> str:
    passed_cases = sum(1 for item in results if item.passed)
    failed_cases = len(results) - passed_cases
    lines = [
        f"Search evaluation project_id={project_id} suite={suite} page_size={page_size}",
        f"Summary: total={len(results)} passed={passed_cases} failed={failed_cases}",
    ]
    for item in results:
        status = "PASS" if item.passed else "FAIL"
        lines.append(
            f"- [{status}] {item.name}: total={item.total} returned={list(item.returned_photo_ids)} reason={item.reason}"
        )
    return "\n".join(lines)


def main() -> None:
    args = _build_parser().parse_args()
    db = SessionLocal()
    try:
        service = SearchEvaluationService(db, args.project_id)
        if args.suite == "planner-debug":
            results = service.evaluate_planner_debug_cases(page_size=args.page_size)
        else:
            results = service.evaluate_default_cases(page_size=args.page_size)
    finally:
        db.close()

    if args.json:
        print(
            json.dumps(
                _serialize_results(args.project_id, args.page_size, results, suite=args.suite),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(_format_text_report(args.project_id, args.page_size, results, suite=args.suite))


if __name__ == "__main__":
    main()
