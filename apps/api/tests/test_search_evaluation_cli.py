from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///ignored.db")
os.environ.setdefault("PHOTO_LIBRARY_PATH", "/tmp")
os.environ.setdefault("THUMBNAIL_PATH", "/tmp")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("OPENAI_BASE_URL", "http://127.0.0.1:9999/v1")
os.environ.setdefault("OPENAI_MODEL", "test-model")
os.environ.setdefault("OPENAI_VISION_MODEL", "test-model")

import run_search_evaluation as cli  # noqa: E402
from app.services.search.search_evaluation_service import SearchEvaluationResult  # noqa: E402


class SearchEvaluationCliTest(unittest.TestCase):
    def test_format_text_report_summarizes_results(self) -> None:
        results = [
            SearchEvaluationResult(
                name="semantic indoor baseline",
                passed=True,
                total=3,
                returned_photo_ids=(1, 2),
                expected_photo_ids=(),
                reason="ok",
            ),
            SearchEvaluationResult(
                name="ocr order number baseline",
                passed=False,
                total=0,
                returned_photo_ids=(),
                expected_photo_ids=(9,),
                reason="missing expected ids: [9]",
            ),
        ]

        report = cli._format_text_report(7, 20, results)

        self.assertIn("project_id=7", report)
        self.assertIn("Summary: total=2 passed=1 failed=1", report)
        self.assertIn("[PASS] semantic indoor baseline", report)
        self.assertIn("[FAIL] ocr order number baseline", report)

    def test_main_runs_default_evaluation_read_only(self) -> None:
        db = MagicMock()
        service = MagicMock()
        service.evaluate_default_cases.return_value = [
            SearchEvaluationResult(
                name="semantic indoor baseline",
                passed=True,
                total=1,
                returned_photo_ids=(1,),
                expected_photo_ids=(),
                reason="ok",
            )
        ]

        with (
            patch("run_search_evaluation.SessionLocal", return_value=db),
            patch("run_search_evaluation.SearchEvaluationService", return_value=service) as service_cls,
            patch("sys.argv", ["run_search_evaluation.py", "--project-id", "7", "--page-size", "8"]),
            patch("builtins.print") as print_mock,
        ):
            cli.main()

        service_cls.assert_called_once_with(db, 7)
        service.evaluate_default_cases.assert_called_once_with(page_size=8)
        db.close.assert_called_once()
        print_mock.assert_called_once()

    def test_main_can_emit_json(self) -> None:
        db = MagicMock()
        service = MagicMock()
        service.evaluate_default_cases.return_value = [
            SearchEvaluationResult(
                name="group photo baseline",
                passed=True,
                total=2,
                returned_photo_ids=(1, 2),
                expected_photo_ids=(),
                reason="ok",
            )
        ]

        with (
            patch("run_search_evaluation.SessionLocal", return_value=db),
            patch("run_search_evaluation.SearchEvaluationService", return_value=service),
            patch("sys.argv", ["run_search_evaluation.py", "--project-id", "3", "--json"]),
            patch("builtins.print") as print_mock,
        ):
            cli.main()

        printed = print_mock.call_args.args[0]
        self.assertIn('"project_id": 3', printed)
        self.assertIn('"failed_cases": 0', printed)


if __name__ == "__main__":
    unittest.main()
