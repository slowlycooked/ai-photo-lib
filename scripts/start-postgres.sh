#!/usr/bin/env bash
# scripts/start-postgres.sh — start local PostgreSQL for ai-photo-lib

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/logs"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Runtime config for loading project env files.
# If this script is moved outside the repo, update these vars at the top only.
ENV_ROOT_DIR="${ENV_ROOT_DIR:-$ROOT}"
ENV_BASE_FILE="${ENV_BASE_FILE:-$ENV_ROOT_DIR/.env}"
ENV_PROFILE_PREFIX="${ENV_PROFILE_PREFIX:-$ENV_ROOT_DIR/.env}"
ENV_DEPLOY_PROFILE="${DEPLOY_PROFILE:-dev}"
POSTGRES_PORT_CONFIG="${POSTGRES_PORT_CONFIG:-}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; RESET='\033[0m'

log_info()  { echo -e "${CYAN}>${RESET} $*"; }
log_ok()    { echo -e "${GREEN}OK${RESET} $*"; }
log_error() { echo -e "${RED}ERR${RESET} $*" >&2; }

pid_file() { echo "$RUN_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

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
if [ -n "$ENV_DEPLOY_PROFILE" ]; then
  CLI_DEPLOY_PROFILE="$ENV_DEPLOY_PROFILE"
fi

load_env_file "$ENV_BASE_FILE"

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

load_env_file "${ENV_PROFILE_PREFIX}.${DEPLOY_PROFILE}"
if [ "$DEPLOY_PROFILE_RAW" != "$DEPLOY_PROFILE" ]; then
  load_env_file "${ENV_PROFILE_PREFIX}.${DEPLOY_PROFILE_RAW}"
fi

POSTGRES_USER="${POSTGRES_USER:-photo}"
POSTGRES_DB="${POSTGRES_DB:-photo}"
if [ -n "$POSTGRES_PORT_CONFIG" ]; then
  POSTGRES_PORT="$POSTGRES_PORT_CONFIG"
else
  POSTGRES_PORT="${POSTGRES_PORT:-${POSTGRES_HOST_PORT:-5432}}"
fi
POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-}"

default_local_state_dir() {
  if [ -n "${DATA_DIR:-}" ]; then
    echo "$DATA_DIR"
  else
    echo "$ROOT/.local"
  fi
}

if [ -z "$POSTGRES_DATA_DIR" ]; then
  POSTGRES_DATA_DIR="$(default_local_state_dir)/postgres"
fi

find_bin() {
  local explicit="$1"
  shift
  if [ -n "$explicit" ]; then
    echo "$explicit"
    return 0
  fi

  local name
  for name in "$@"; do
    if command -v "$name" >/dev/null 2>&1; then
      command -v "$name"
      return 0
    fi
  done
  return 1
}

POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR%/}"
INITDB_BIN="$(find_bin "${POSTGRES_BIN_DIR:+$POSTGRES_BIN_DIR/initdb}" initdb || true)"
PG_CTL_BIN="$(find_bin "${POSTGRES_BIN_DIR:+$POSTGRES_BIN_DIR/pg_ctl}" pg_ctl || true)"
PG_ISREADY_BIN="$(find_bin "${POSTGRES_BIN_DIR:+$POSTGRES_BIN_DIR/pg_isready}" pg_isready || true)"
PSQL_BIN="$(find_bin "${POSTGRES_BIN_DIR:+$POSTGRES_BIN_DIR/psql}" psql || true)"
CREATEDB_BIN="$(find_bin "${POSTGRES_BIN_DIR:+$POSTGRES_BIN_DIR/createdb}" createdb || true)"

require_postgres_tools() {
  local missing=0
  for bin_var in INITDB_BIN PG_CTL_BIN PG_ISREADY_BIN PSQL_BIN CREATEDB_BIN; do
    if [ -z "${!bin_var}" ]; then
      log_error "缺少 PostgreSQL 工具: ${bin_var%_BIN}。请先安装 postgresql@17 与 pgvector，或在 .env 中配置 POSTGRES_BIN_DIR"
      missing=1
    fi
  done
  [ "$missing" -eq 0 ]
}

detect_postgres_locale_mismatch() {
  local conf="$POSTGRES_DATA_DIR/postgresql.conf"
  [ -f "$conf" ] || return 1

  local bad_lines=""
  bad_lines="$(rg -n "lc_(messages|monetary|numeric|time)\s*=\s*'[^']*\.utf8'" "$conf" 2>/dev/null || true)"
  [ -n "$bad_lines" ]
}

show_postgres_repair_hint() {
  log_error "检测到现有 PostgreSQL 数据目录很可能来自 Docker/Linux，locale 配置与 macOS 不兼容。"
  log_error "当前数据目录: $POSTGRES_DATA_DIR"
  echo ""
  echo "建议二选一："
  echo "  1. 开发环境且数据不重要：改用新的原生数据目录，例如在 .env 中设置 POSTGRES_DATA_DIR=$ROOT/.local/postgres"
  echo "  2. 需要保留现有数据：修复 $POSTGRES_DATA_DIR/postgresql.conf 中的 locale 配置，再启动并做迁移/导出"
  echo ""
  echo "当前常见不兼容项是："
  echo "  lc_messages = 'en_US.utf8'"
  echo "  lc_monetary = 'en_US.utf8'"
  echo "  lc_numeric  = 'en_US.utf8'"
  echo "  lc_time     = 'en_US.utf8'"
  echo ""
  echo "在 macOS 上通常需要改为："
  echo "  en_US.UTF-8"
  echo ""
}

postgres_pid_from_data_dir() {
  local pid_path="$POSTGRES_DATA_DIR/postmaster.pid"
  if [ -f "$pid_path" ]; then
    head -n 1 "$pid_path"
  fi
}

postgres_is_ready() {
  [ -n "$PG_ISREADY_BIN" ] || return 1
  "$PG_ISREADY_BIN" -h 127.0.0.1 -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1
}

get_listen_pid_by_port() {
  local port="$1"
  { lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true; } | awk 'NR==2{print $2}'
}

save_pid() {
  echo "$1" > "$(pid_file "$2")"
}

wait_for_postgres() {
  local timeout="${1:-30}"
  local waited=0
  until postgres_is_ready; do
    if [ "$waited" -ge "$timeout" ]; then
      log_error "PostgreSQL 在 ${timeout}s 内未就绪，请查看 $(log_file postgres)"
      return 1
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 0
}

init_postgres_cluster() {
  if [ -f "$POSTGRES_DATA_DIR/PG_VERSION" ]; then
    return 0
  fi

  mkdir -p "$(dirname "$POSTGRES_DATA_DIR")"
  log_info "初始化 PostgreSQL 数据目录: $POSTGRES_DATA_DIR"
  "$INITDB_BIN" -D "$POSTGRES_DATA_DIR" -U "$POSTGRES_USER" --auth=trust >/dev/null
}

ensure_postgres_db() {
  local exists=""
  exists="$("$PSQL_BIN" \
    -h 127.0.0.1 \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    -tAc "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'" \
    2>/dev/null || true)"

  if [ "$exists" = "1" ]; then
    return 0
  fi

  log_info "创建数据库: $POSTGRES_DB"
  "$CREATEDB_BIN" -h 127.0.0.1 -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB"
}

start_postgres() {
  require_postgres_tools || return 1

  if postgres_is_ready; then
    local listen_pid=""
    listen_pid="$(get_listen_pid_by_port "$POSTGRES_PORT")"
    if [ -n "$listen_pid" ]; then
      log_ok "postgres 已可用 (PID $listen_pid, port $POSTGRES_PORT)"
    else
      log_ok "postgres 已可用 (port $POSTGRES_PORT)"
    fi
    return 0
  fi

  local occupied_pid=""
  occupied_pid="$(get_listen_pid_by_port "$POSTGRES_PORT")"
  if [ -n "$occupied_pid" ]; then
    local occupied_cmd=""
    occupied_cmd="$(ps -p "$occupied_pid" -o command= 2>/dev/null || true)"
    log_error "端口 $POSTGRES_PORT 已被占用 (PID $occupied_pid): $occupied_cmd"
    return 1
  fi

  init_postgres_cluster

  log_info "启动 PostgreSQL (port $POSTGRES_PORT)..."
  if ! "$PG_CTL_BIN" \
    -D "$POSTGRES_DATA_DIR" \
    -l "$(log_file postgres)" \
    -o "-p $POSTGRES_PORT -h 127.0.0.1" \
    start >/dev/null; then
    if detect_postgres_locale_mismatch; then
      show_postgres_repair_hint
    fi
    log_error "postgres 启动失败，请查看 $(log_file postgres)"
    return 1
  fi

  wait_for_postgres 30
  ensure_postgres_db

  local pg_pid=""
  pg_pid="$(postgres_pid_from_data_dir)"
  if [ -n "$pg_pid" ]; then
    save_pid "$pg_pid" postgres
  fi

  log_ok "postgres 已启动 (data=$POSTGRES_DATA_DIR, port $POSTGRES_PORT)"
}

stop_postgres() {
  if [ -z "$PG_CTL_BIN" ]; then
    log_error "缺少 PostgreSQL 工具: PG_CTL。请先安装 postgresql@17 或在 .env 中配置 POSTGRES_BIN_DIR"
    return 1
  fi

  local pg_pid=""
  pg_pid="$(postgres_pid_from_data_dir)"
  if [ -n "$pg_pid" ] && kill -0 "$pg_pid" 2>/dev/null; then
    log_info "停止 PostgreSQL (PID $pg_pid)..."
    "$PG_CTL_BIN" -D "$POSTGRES_DATA_DIR" stop -m fast >/dev/null || true
    rm -f "$(pid_file postgres)"
    log_ok "postgres 已停止"
    return 0
  fi

  if postgres_is_ready; then
    local listen_pid=""
    listen_pid="$(get_listen_pid_by_port "$POSTGRES_PORT")"
    log_error "检测到 PostgreSQL 正在端口 $POSTGRES_PORT 运行 (PID ${listen_pid:-?})，但不属于当前 POSTGRES_DATA_DIR: $POSTGRES_DATA_DIR"
    log_error "请切换到对应实例的数据目录后再停止，或手动停止该实例。"
    return 1
  fi

  log_info "postgres 未在运行"
}

restart_postgres() {
  stop_postgres
  start_postgres
}

show_help() {
  echo "用法: ./scripts/start-postgres.sh [start|stop|restart|help]"
  echo ""
  echo "命令:"
  echo "  start    启动 PostgreSQL（默认）"
  echo "  stop     停止当前 POSTGRES_DATA_DIR 对应的 PostgreSQL"
  echo "  restart  重启 PostgreSQL"
  echo "  help     显示帮助"
}

COMMAND="${1:-start}"

case "$COMMAND" in
  start)
    start_postgres
    ;;
  stop)
    stop_postgres
    ;;
  restart)
    restart_postgres
    ;;
  help|--help|-h)
    show_help
    ;;
  *)
    log_error "未知命令: $COMMAND"
    show_help
    exit 1
    ;;
esac
