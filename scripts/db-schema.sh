#!/usr/bin/env bash
# scripts/db-schema.sh — database schema check and update tool for ai-photo-lib
#
# Usage:
#   ./scripts/db-schema.sh check        # inspect migration state, report issues
#   ./scripts/db-schema.sh upgrade      # run alembic upgrade head
#   ./scripts/db-schema.sh verify       # deep column/constraint verification
#   ./scripts/db-schema.sh all          # check + verify (default)
#   ./scripts/db-schema.sh fix-version  # fix duplicate rows in alembic_version
#
# The script loads .env from the project root and runs the Python tool under
# apps/api/. All configuration (DATABASE_URL, etc.) must be in .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_DIR="$ROOT/apps/api"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# ── Load .env (+ optional profile overlay) ──────────────────────────────────
load_env_file() {
  local path="$1"
  if [ -f "$path" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$path"
    set +a
  fi
}

CLI_DEPLOY_PROFILE="${DEPLOY_PROFILE:-}"
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  load_env_file "$ENV_FILE"
else
  echo -e "${RED}ERROR: .env file not found at $ENV_FILE${RESET}" >&2
  echo "Create .env from .env.example and set DATABASE_URL." >&2
  exit 1
fi

if [ -n "$CLI_DEPLOY_PROFILE" ]; then
  DEPLOY_PROFILE="$CLI_DEPLOY_PROFILE"
fi

DEPLOY_PROFILE="${DEPLOY_PROFILE:-dev}"
DEPLOY_PROFILE_RAW="$DEPLOY_PROFILE"
DEPLOY_PROFILE_LOWER="$(printf '%s' "$DEPLOY_PROFILE" | tr '[:upper:]' '[:lower:]')"
case "$DEPLOY_PROFILE_LOWER" in
  prod|production|runtime|prd)
    DEPLOY_PROFILE="prd"
    ;;
  dev)
    DEPLOY_PROFILE="dev"
    ;;
esac

load_env_file "$ROOT/.env.$DEPLOY_PROFILE"
if [ "$DEPLOY_PROFILE_RAW" != "$DEPLOY_PROFILE" ]; then
  load_env_file "$ROOT/.env.$DEPLOY_PROFILE_RAW"
fi

if [ -z "${DATABASE_URL:-}" ]; then
  echo -e "${RED}ERROR: DATABASE_URL is not set in .env${RESET}" >&2
  exit 1
fi

# ── Resolve Python interpreter ────────────────────────────────────────────────
# Prefer the virtualenv under apps/api/, then fall back to system python3.
VENV_PYTHON="$API_DIR/.venv/bin/python"
if [ -x "$VENV_PYTHON" ]; then
  PYTHON="$VENV_PYTHON"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  echo -e "${RED}ERROR: No Python interpreter found.${RESET}" >&2
  echo "Install Python 3 or create a virtualenv at apps/api/.venv." >&2
  exit 1
fi

PYTHON_VERSION=$("$PYTHON" --version 2>&1)
echo -e "${CYAN}▶${RESET} Using: ${BOLD}$PYTHON_VERSION${RESET}  ($PYTHON)"

# ── Dispatch ──────────────────────────────────────────────────────────────────
CMD="${1:-all}"

case "$CMD" in
  check|upgrade|verify|all|fix-version)
    ;;
  help|--help|-h)
    sed -n '2,10p' "$0"   # print the usage comment block
    exit 0
    ;;
  *)
    echo -e "${RED}Unknown command: $CMD${RESET}" >&2
    echo "Valid commands: check  upgrade  verify  all  fix-version" >&2
    exit 1
    ;;
esac

echo -e "${CYAN}▶${RESET} Command : ${BOLD}$CMD${RESET}"
echo -e "${CYAN}▶${RESET} API dir : ${BOLD}$API_DIR${RESET}"
echo

cd "$API_DIR"
exec "$PYTHON" db_schema_check.py "$CMD"
