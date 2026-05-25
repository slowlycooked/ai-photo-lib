#!/usr/bin/env bash
# scripts/bootstrap-macos.sh — prepare a native macOS environment
#
# Usage:
#   ./scripts/bootstrap-macos.sh
#   DEPLOY_PROFILE=runtime ./scripts/bootstrap-macos.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

DEPLOY_PROFILE="${DEPLOY_PROFILE:-dev}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-${DATA_DIR:-$ROOT/.local}/postgres17}"
THUMBNAIL_PATH="${THUMBNAIL_PATH:-${DATA_DIR:-$ROOT/.local}/thumbs}"
POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-/opt/homebrew/opt/postgresql@17/bin}"

say() { echo "[bootstrap] $*"; }
warn() { echo "[bootstrap][warn] $*" >&2; }

require_cmd() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    warn "缺少命令: $cmd"
    warn "建议安装: $hint"
    exit 1
  fi
}

require_file() {
  local path="$1"
  local hint="$2"
  if [ ! -x "$path" ] && [ ! -f "$path" ]; then
    warn "缺少文件: $path"
    warn "建议安装: $hint"
    exit 1
  fi
}

say "profile=$DEPLOY_PROFILE"

require_cmd python3 "brew install python@3.11"
require_cmd node "brew install node@20"
require_cmd npm "brew install node@20"
require_file "$POSTGRES_BIN_DIR/initdb" "brew install postgresql@17 pgvector"
require_file "$POSTGRES_BIN_DIR/pg_ctl" "brew install postgresql@17 pgvector"
require_file "$POSTGRES_BIN_DIR/psql" "brew install postgresql@17 pgvector"
require_file "$("$POSTGRES_BIN_DIR/pg_config" --sharedir)/extension/vector.control" "brew install postgresql@17 pgvector"

mkdir -p "$POSTGRES_DATA_DIR" "$THUMBNAIL_PATH" "$ROOT/.logs" "$ROOT/.run"

if [ ! -d "$ROOT/apps/api/.venv" ]; then
  say "创建 API 虚拟环境..."
  python3 -m venv "$ROOT/apps/api/.venv"
fi

say "安装 API 依赖..."
"$ROOT/apps/api/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"$ROOT/apps/api/.venv/bin/python" -m pip install -r "$ROOT/apps/api/requirements.txt"

say "安装 Web 依赖..."
cd "$ROOT/apps/web"
npm install

say "完成。接下来可以执行:"
echo "  ./scripts/svc.sh start"
