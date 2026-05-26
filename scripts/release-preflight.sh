#!/usr/bin/env bash
# scripts/release-preflight.sh — Week4 release preflight checks

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$ROOT/apps/api"
WEB_DIR="$ROOT/apps/web"
PYTHON_BIN="$ROOT/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERROR: Python venv not found at $PYTHON_BIN" >&2
  echo "Please run bootstrap first: ./scripts/bootstrap-macos.sh" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm not found in PATH" >&2
  exit 1
fi

echo "[preflight] 1/3 backend release guard and core regressions"
cd "$API_DIR"
"$PYTHON_BIN" -m pytest \
  tests/test_release_audit_guards.py \
  tests/test_project_isolation_endpoints.py \
  tests/test_project_task_app_service.py \
  tests/test_project_people_endpoints.py \
  tests/test_people_learning_service.py \
  -q

echo "[preflight] 2/3 frontend maturity rendering regressions"
cd "$WEB_DIR"
npm test -- \
  src/components/common/CapabilityMaturityBadge.test.tsx \
  src/components/project-ai-settings/PromptSettingsSection.test.tsx \
  src/pages/TasksPage.test.tsx

echo "[preflight] 3/3 frontend build"
npm run build

echo "[preflight] PASS"
