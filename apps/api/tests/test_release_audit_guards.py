from __future__ import annotations

import ast
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.config import Settings, enforce_managed_config_keys, get_unknown_config_keys
from app.services.aijob_app_service import AIJobAppService


_API_TESTS_DIR = Path(__file__).resolve().parent
_API_ROOT = _API_TESTS_DIR.parent
_REPO_ROOT = _API_ROOT.parent.parent


class ReleaseChecklistConsistencyTest(unittest.TestCase):
    def _parse_maturity_from_ts(self, text: str) -> dict[str, str]:
        rows: dict[str, str] = {}
        block_pattern = re.compile(
            r"capability:\s*\"([^\"]+)\"[\s\S]*?levelLabel:\s*\"([^\"]+)\"",
            re.MULTILINE,
        )
        for capability, level in block_pattern.findall(text):
            rows[capability.strip()] = level.strip()
        return rows

    def _parse_maturity_from_markdown(self, text: str) -> dict[str, str]:
        rows: dict[str, str] = {}
        row_pattern = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
        for capability, level in row_pattern.findall(text):
            capability = capability.strip()
            level = level.strip()
            if capability in {"能力", "------"}:
                continue
            if capability in {
                "Face clustering",
                "Face rematch unknown",
                "Search face filters",
                "Task controls",
                "System health check",
                "Prompt 测试",
                "Embedding rebuild",
            }:
                rows[capability] = level
        return rows

    def test_release_docs_and_frontend_maturity_catalog_are_consistent(self) -> None:
        catalog_path = _REPO_ROOT / "apps/web/src/lib/capabilityMaturity.ts"
        readme_path = _REPO_ROOT / "README.md"
        checklist_path = _REPO_ROOT / "Runbook/release-checklist.md"

        catalog = self._parse_maturity_from_ts(catalog_path.read_text(encoding="utf-8"))
        readme = self._parse_maturity_from_markdown(readme_path.read_text(encoding="utf-8"))
        checklist = self._parse_maturity_from_markdown(checklist_path.read_text(encoding="utf-8"))

        expected = {
            "Face clustering": "稳定",
            "Face rematch unknown": "稳定",
            "Search face filters": "稳定",
            "Task controls": "稳定",
            "System health check": "稳定",
            "Prompt 测试": "稳定",
            "Embedding rebuild": "稳定",
        }
        self.assertEqual(catalog, expected)
        self.assertEqual(readme, expected)
        self.assertEqual(checklist, expected)


class ProjectScopeAuditTest(unittest.TestCase):
    def test_project_scoped_routes_exist_for_week4_capabilities(self) -> None:
        router_specs = [
            ("project_faces.py", "/{project_id}/face-cluster-unknown"),
            ("project_prompt_templates.py", "/{project_id}/prompt-templates/test"),
            ("project_embeddings.py", "/{project_id}/embeddings/rebuild"),
        ]

        for file_name, expected_path in router_specs:
            path = _API_ROOT / "app" / "routers" / file_name
            text = path.read_text(encoding="utf-8")
            self.assertIn(expected_path, text)


class ConfigurationGuardTest(unittest.TestCase):
    def test_missing_required_config_fails_explicitly(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None)

    def test_unknown_config_keys_detected_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "DATABASE_URL=sqlite:///tmp.db\n"
                "PHOTO_LIBRARY_PATH=/tmp\n"
                "THUMBNAIL_PATH=/tmp\n"
                "OPENAI_API_KEY=test\n"
                "OPENAI_BASE_URL=http://127.0.0.1:9999/v1\n"
                "OPENAI_MODEL=test-model\n"
                "OPENAI_VISION_MODEL=test-model\n"
                "UNEXPECTED_FLAG=1\n",
                encoding="utf-8",
            )
            unknown = get_unknown_config_keys(env_path)
        self.assertEqual(unknown, ["UNEXPECTED_FLAG"])

    def test_unknown_managed_config_keys_fail_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "DATABASE_URL=sqlite:///tmp.db\n"
                "PHOTO_LIBRARY_PATH=/tmp\n"
                "THUMBNAIL_PATH=/tmp\n"
                "OPENAI_API_KEY=test\n"
                "OPENAI_BASE_URL=http://127.0.0.1:9999/v1\n"
                "OPENAI_MODEL=test-model\n"
                "OPENAI_VISION_MODEL=test-model\n"
                "OPENAI_MODEL_ALIAS=demo\n",
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                enforce_managed_config_keys(env_path)

    def test_non_managed_unknown_keys_do_not_fail_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / ".env"
            env_path.write_text(
                "DATABASE_URL=sqlite:///tmp.db\n"
                "PHOTO_LIBRARY_PATH=/tmp\n"
                "THUMBNAIL_PATH=/tmp\n"
                "OPENAI_API_KEY=test\n"
                "OPENAI_BASE_URL=http://127.0.0.1:9999/v1\n"
                "OPENAI_MODEL=test-model\n"
                "OPENAI_VISION_MODEL=test-model\n"
                "WEB_PORT=8088\n",
                encoding="utf-8",
            )
            self.assertEqual(get_unknown_config_keys(env_path, managed_only=True), [])


class WorkerProjectIdGuardTest(unittest.TestCase):
    def test_aijob_rejects_missing_project_id(self) -> None:
        class _SessionStub:
            def __init__(self) -> None:
                self.commit_calls = 0

            def commit(self) -> None:
                self.commit_calls += 1

        db = _SessionStub()
        service = AIJobAppService(db)  # type: ignore[arg-type]

        job = SimpleNamespace(
            id=9001,
            photo_id=42,
            project_id=None,
            status="queued",
            error_message=None,
            finished_at=None,
            updated_at=None,
        )

        service.process_job(job)  # type: ignore[arg-type]

        self.assertEqual(job.status, "failed")
        self.assertIn("has no project_id", job.error_message)
        self.assertEqual(db.commit_calls, 1)


class StaticQualityGuardTest(unittest.TestCase):
    _COMPLEXITY_NODE_TYPES = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.BoolOp,
        ast.IfExp,
        ast.ExceptHandler,
    )

    def _max_function_complexity(self, path: Path) -> int:
        root = ast.parse(path.read_text(encoding="utf-8"))
        max_score = 0
        for node in ast.walk(root):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            score = 1
            for child in ast.walk(node):
                if isinstance(child, self._COMPLEXITY_NODE_TYPES):
                    if isinstance(child, ast.BoolOp):
                        score += max(len(child.values) - 1, 1)
                    else:
                        score += 1
            max_score = max(max_score, score)
        return max_score

    @staticmethod
    def _annotation_uses_pep604_union(node: ast.AST) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.BinOp) and isinstance(child.op, ast.BitOr):
                return True
        return False

    def _file_uses_pep604_union_annotation(self, path: Path) -> bool:
        root = ast.parse(path.read_text(encoding="utf-8"))
        annotations: list[ast.AST] = []

        for node in ast.walk(root):
            if isinstance(node, ast.AnnAssign) and node.annotation is not None:
                annotations.append(node.annotation)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is not None:
                    annotations.append(node.returns)

                args = []
                args.extend(node.args.args)
                args.extend(node.args.kwonlyargs)
                args.extend(node.args.posonlyargs)
                if node.args.vararg is not None:
                    args.append(node.args.vararg)
                if node.args.kwarg is not None:
                    args.append(node.args.kwarg)

                for arg in args:
                    if arg.annotation is not None:
                        annotations.append(arg.annotation)

        return any(self._annotation_uses_pep604_union(node) for node in annotations)

    def test_complexity_budget_for_people_and_task_orchestration(self) -> None:
        budgets = {
            "app/routers/project_people.py": 4,
            "app/services/people_assignment_mutation_service.py": 1,
            "app/services/people_audit_service.py": 3,
            "app/services/people_batch_review_service.py": 4,
            "app/services/people_lifecycle_mutation_service.py": 1,
            "app/services/people_mutation_service.py": 4,
            "app/services/person_assignment_workflow_service.py": 10,
            "app/services/person_lifecycle_mutation_service.py": 10,
            "app/services/people_learning_service.py": 18,
            "app/services/people_query_service.py": 12,
            "app/services/search/people_recall.py": 14,
            "app/services/project_task_app_service.py": 12,
            "app/services/project_task_handlers.py": 8,
        }
        for relative_path, threshold in budgets.items():
            score = self._max_function_complexity(_API_ROOT / relative_path)
            self.assertLessEqual(score, threshold, f"{relative_path} complexity={score} > {threshold}")

    def test_people_router_uses_focused_services(self) -> None:
        path = _API_ROOT / "app/routers/project_people.py"
        text = path.read_text(encoding="utf-8")

        self.assertIn("PeopleQueryService", text)
        self.assertIn("PeopleAssignmentMutationService", text)
        self.assertIn("PeopleLifecycleMutationService", text)
        self.assertIn("PeopleBatchReviewService", text)
        self.assertIn("PeopleAuditService", text)
        self.assertNotIn("PeopleMutationService", text)
        self.assertNotIn("PeopleBatchRetryExhausted", text)
        self.assertNotIn("HTTPException", text)
        self.assertNotIn("execute_batch_with_retry", text)

    def test_people_status_literals_are_centralized(self) -> None:
        recall_path = _API_ROOT / "app/services/search/people_recall.py"
        recall_text = recall_path.read_text(encoding="utf-8")

        self.assertIn("from ..people_assignment_constants import", recall_text)
        self.assertNotIn("ALLOWED_ASSIGNMENT_STATUSES", recall_text)
        self.assertNotIn("ASSIGNMENT_STATUS_WEIGHT: dict", recall_text)

    def test_people_mutation_and_cluster_status_literals_are_centralized(self) -> None:
        targets = [
            _API_ROOT / "app/services/person_assignment_workflow_service.py",
            _API_ROOT / "app/services/person_lifecycle_mutation_service.py",
            _API_ROOT / "app/services/unknown_face_clustering_service.py",
        ]
        pattern = re.compile(
            r"assignment_status\s*(?:==|!=|=)\s*\""
            r"(review_pending|auto_assigned|human_confirmed|human_corrected|rejected)\""
            r"|status\s*=\s*\"(human_confirmed|human_corrected|rejected)\""
        )

        for path in targets:
            text = path.read_text(encoding="utf-8")
            self.assertIn("people_assignment_constants", text)
            self.assertEqual(
                pattern.findall(text),
                [],
                f"Found hardcoded assignment status literal in {path}",
            )

    def test_critical_services_avoid_pep604_union_type_syntax(self) -> None:
        targets = [
            _API_ROOT / "app/services/people_mutation_service.py",
            _API_ROOT / "app/services/people_assignment_mutation_service.py",
            _API_ROOT / "app/services/people_audit_service.py",
            _API_ROOT / "app/services/people_batch_review_service.py",
            _API_ROOT / "app/services/people_lifecycle_mutation_service.py",
            _API_ROOT / "app/services/person_assignment_workflow_service.py",
            _API_ROOT / "app/services/person_lifecycle_mutation_service.py",
            _API_ROOT / "app/services/people_learning_service.py",
            _API_ROOT / "app/services/people_query_service.py",
            _API_ROOT / "app/services/project_task_app_service.py",
            _API_ROOT / "app/services/project_task_handlers.py",
            _API_ROOT / "app/services/unknown_face_clustering_service.py",
            _API_ROOT / "app/services/search/people_recall.py",
        ]

        for path in targets:
            self.assertFalse(
                self._file_uses_pep604_union_annotation(path),
                f"Found PEP 604 union annotation in {path}; use typing.Optional/typing.Union for py3.9 compatibility",
            )

    def test_critical_routers_and_schemas_avoid_pep604_union_type_syntax(self) -> None:
        targets = [
            _API_ROOT / "app/routers/project_faces.py",
            _API_ROOT / "app/routers/project_prompt_templates.py",
            _API_ROOT / "app/routers/project_embeddings.py",
            _API_ROOT / "app/routers/project_embedding_settings.py",
            _API_ROOT / "app/schemas/face.py",
            _API_ROOT / "app/schemas/project_search_settings.py",
            _API_ROOT / "app/schemas/project_ai.py",
        ]

        for path in targets:
            self.assertFalse(
                self._file_uses_pep604_union_annotation(path),
                f"Found PEP 604 union annotation in {path}; use typing.Optional/typing.Union for py3.9 compatibility",
            )

    def test_vector_recall_does_not_fallback_to_global_embedding_settings(self) -> None:
        path = _API_ROOT / "app/services/search/vector_recall.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("resolve_embedding_settings_strict", text)
        self.assertNotIn("global_settings.embedding_base_url or global_settings.openai_base_url", text)

    def test_aijob_embedding_does_not_fallback_to_ai_endpoint(self) -> None:
        path = _API_ROOT / "app/services/aijob_app_service.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("resolve_embedding_settings_strict", text)
        self.assertNotIn("embed_endpoint = ai_settings.endpoint_url", text)

    def test_aijob_analysis_uses_strict_project_ai_settings(self) -> None:
        path = _API_ROOT / "app/services/aijob_app_service.py"
        text = path.read_text(encoding="utf-8")
        self.assertIn("get_project_ai_settings_strict", text)
        self.assertIn("get_active_prompt_template_strict", text)
        self.assertNotIn("get_or_create_project_ai_settings", text)

    def test_scanner_no_default_project_path_fallback(self) -> None:
        path = _API_ROOT / "app/services/scanner.py"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("fallback to settings.photo_library_path", text)
        self.assertNotIn("fallback to settings.host_photo_library_path", text)
        self.assertNotIn("fallback to settings.thumbnail_path", text)


if __name__ == "__main__":
    unittest.main()
