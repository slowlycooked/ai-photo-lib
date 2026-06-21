#!/usr/bin/env bash
# scripts/bootstrap-macos.sh — prepare a native macOS environment
#
# Usage:
#   ./scripts/bootstrap-macos.sh
#   DEPLOY_PROFILE=runtime ./scripts/bootstrap-macos.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

say() { echo "[bootstrap] $*"; }
warn() { echo "[bootstrap][warn] $*" >&2; }

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
load_env_file "$ROOT/.env"

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

detect_postgres_bin_dir() {
  # Respect explicit user/project overrides first.
  if [ -n "${POSTGRES_BIN_DIR:-}" ] && [ -x "${POSTGRES_BIN_DIR}/pg_config" ]; then
    printf '%s\n' "$POSTGRES_BIN_DIR"
    return 0
  fi

  local candidates=()

  if command -v brew >/dev/null 2>&1; then
    local brew_prefix
    local versioned_dir
    brew_prefix="$(brew --prefix 2>/dev/null || true)"
    if [ -n "$brew_prefix" ]; then
      for versioned_dir in "$brew_prefix"/opt/postgresql@*/bin; do
        if [ -x "$versioned_dir/pg_config" ]; then
          candidates+=("$versioned_dir")
        fi
      done
      candidates+=("$brew_prefix/opt/postgresql/bin")
    fi
  fi

  # Fallback for machines where Homebrew prefix lookup is unavailable.
  local fallback_base
  for fallback_base in "/opt/homebrew" "/usr/local"; do
    local versioned_fallback
    for versioned_fallback in "$fallback_base"/opt/postgresql@*/bin; do
      if [ -x "$versioned_fallback/pg_config" ]; then
        candidates+=("$versioned_fallback")
      fi
    done
    candidates+=("$fallback_base/opt/postgresql/bin")
  done

  local candidate
  for candidate in "${candidates[@]}"; do
    if [ -x "$candidate/pg_config" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  if command -v pg_config >/dev/null 2>&1; then
    dirname "$(command -v pg_config)"
    return 0
  fi

  return 1
}

POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-$(detect_postgres_bin_dir || true)}"

if [ -z "$POSTGRES_BIN_DIR" ]; then
  warn "无法自动检测 POSTGRES_BIN_DIR，请先安装 PostgreSQL（brew install postgresql pgvector）"
  warn "或者手动设置环境变量 POSTGRES_BIN_DIR 后重试"
  exit 1
fi

POSTGRES_VERSION_RAW="$($POSTGRES_BIN_DIR/pg_config --version 2>/dev/null || true)"
POSTGRES_MAJOR_VERSION="$(printf '%s' "$POSTGRES_VERSION_RAW" | sed -E 's/.* ([0-9]+)(\.[0-9]+)?.*/\1/' )"
if ! [[ "$POSTGRES_MAJOR_VERSION" =~ ^[0-9]+$ ]]; then
  POSTGRES_MAJOR_VERSION=""
fi

POSTGRES_DATA_SUFFIX="postgres"
if [ -n "$POSTGRES_MAJOR_VERSION" ]; then
  POSTGRES_DATA_SUFFIX="postgres$POSTGRES_MAJOR_VERSION"
fi

POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-${DATA_DIR:-$ROOT/.local}/$POSTGRES_DATA_SUFFIX}"
THUMBNAIL_PATH="${THUMBNAIL_PATH:-${DATA_DIR:-$ROOT/.local}/thumbs}"

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

require_cmd python3 "brew install python 或安装任意可用的 python3"
require_cmd node "brew install node 或安装任意可用的 node"
require_cmd npm "安装 node（通常会自带 npm）"
require_file "$POSTGRES_BIN_DIR/initdb" "brew install postgresql pgvector"
require_file "$POSTGRES_BIN_DIR/pg_ctl" "brew install postgresql pgvector"
require_file "$POSTGRES_BIN_DIR/psql" "brew install postgresql pgvector"
require_file "$("$POSTGRES_BIN_DIR/pg_config" --sharedir)/extension/vector.control" "brew install postgresql pgvector"

mkdir -p "$POSTGRES_DATA_DIR" "$THUMBNAIL_PATH" "$ROOT/logs" "$ROOT/.run"

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
