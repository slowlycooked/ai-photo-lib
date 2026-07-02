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
ENV_ROOT_DIR="${ENV_ROOT_DIR:-}"
ENV_BASE_FILE="${ENV_BASE_FILE:-}"
ENV_PROFILE_PREFIX="${ENV_PROFILE_PREFIX:-}"
ENV_DEPLOY_PROFILE="${ENV_DEPLOY_PROFILE:-}"
POSTGRES_PORT_CONFIG="${POSTGRES_PORT_CONFIG:-}"
POSTGRES_HOST_CONFIG="${POSTGRES_HOST_CONFIG:-}"
LOCAL_ENV_FILE="${LOCAL_ENV_FILE:-$SCRIPT_DIR/.env}"
POSTGRES_CONF_FILE="${POSTGRES_CONF_FILE:-}"

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

trim_value() {
  local v="$1"
  v="${v#${v%%[![:space:]]*}}"
  v="${v%${v##*[![:space:]]}}"
  printf '%s' "$v"
}

read_conf_value() {
  local file="$1"
  local key="$2"
  [ -f "$file" ] || return 1

  local line=""
  line="$(grep -E "^[[:space:]]*$key[[:space:]]*=" "$file" | tail -n 1 || true)"
  [ -n "$line" ] || return 1

  local value="${line#*=}"
  value="${value%%#*}"
  value="$(trim_value "$value")"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  value="$(trim_value "$value")"

  [ -n "$value" ] || return 1
  printf '%s' "$value"
}

read_env_value() {
  local file="$1"
  local key="$2"
  [ -f "$file" ] || return 1

  local line=""
  line="$(grep -E "^[[:space:]]*$key[[:space:]]*=" "$file" | tail -n 1 || true)"
  [ -n "$line" ] || return 1

  local value="${line#*=}"
  value="${value%%#*}"
  value="$(trim_value "$value")"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  value="$(trim_value "$value")"

  [ -n "$value" ] || return 1
  printf '%s' "$value"
}

CLI_DEPLOY_PROFILE="${DEPLOY_PROFILE:-}"
# Load local .env first so script-local overrides (e.g. ENV_ROOT_DIR / POSTGRES_PORT_CONFIG) take effect.
load_env_file "$LOCAL_ENV_FILE"

ENV_ROOT_DIR="${ENV_ROOT_DIR:-$ROOT}"
ENV_BASE_FILE="${ENV_BASE_FILE:-$ENV_ROOT_DIR/.env}"
ENV_PROFILE_PREFIX="${ENV_PROFILE_PREFIX:-$ENV_ROOT_DIR/.env}"
ENV_DEPLOY_PROFILE="${ENV_DEPLOY_PROFILE:-${DEPLOY_PROFILE:-dev}}"
POSTGRES_CONF_FILE="${POSTGRES_CONF_FILE:-$ENV_ROOT_DIR/postgresql.conf}"

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
POSTGRES_CONF_PORT="$(read_conf_value "$POSTGRES_CONF_FILE" port || true)"
POSTGRES_CONF_LISTEN_ADDRESSES="$(read_conf_value "$POSTGRES_CONF_FILE" listen_addresses || true)"
POSTGRES_CONF_DATA_DIR="$(read_conf_value "$POSTGRES_CONF_FILE" data_directory || true)"
LOCAL_ENV_POSTGRES_PORT_CONFIG="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_PORT_CONFIG || true)"
LOCAL_ENV_POSTGRES_HOST_CONFIG="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_HOST_CONFIG || true)"
LOCAL_ENV_POSTGRES_HOST="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_HOST || true)"
LOCAL_ENV_POSTGRES_LISTEN_HOST="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_LISTEN_HOST || true)"
LOCAL_ENV_POSTGRES_CONNECT_HOST="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_CONNECT_HOST || true)"
LOCAL_ENV_POSTGRES_PORT="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_PORT || true)"
LOCAL_ENV_POSTGRES_HOST_PORT="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_HOST_PORT || true)"
LOCAL_ENV_POSTGRES_DATA_DIR="$(read_env_value "$LOCAL_ENV_FILE" POSTGRES_DATA_DIR || true)"

POSTGRES_PORT_SOURCE=""
POSTGRES_LISTEN_HOST_SOURCE=""
POSTGRES_CONNECT_HOST_SOURCE=""
POSTGRES_DATA_DIR_SOURCE=""

if [ -n "$POSTGRES_PORT_CONFIG" ]; then
  POSTGRES_PORT="$POSTGRES_PORT_CONFIG"
  POSTGRES_PORT_SOURCE="POSTGRES_PORT_CONFIG"
elif [ -n "$POSTGRES_CONF_PORT" ]; then
  POSTGRES_PORT="$POSTGRES_CONF_PORT"
  POSTGRES_PORT_SOURCE="postgresql.conf:port"
elif [ -n "$LOCAL_ENV_POSTGRES_PORT_CONFIG" ]; then
  POSTGRES_PORT="$LOCAL_ENV_POSTGRES_PORT_CONFIG"
  POSTGRES_PORT_SOURCE="local .env:POSTGRES_PORT_CONFIG"
elif [ -n "$LOCAL_ENV_POSTGRES_PORT" ]; then
  POSTGRES_PORT="$LOCAL_ENV_POSTGRES_PORT"
  POSTGRES_PORT_SOURCE="local .env:POSTGRES_PORT"
elif [ -n "$LOCAL_ENV_POSTGRES_HOST_PORT" ]; then
  POSTGRES_PORT="$LOCAL_ENV_POSTGRES_HOST_PORT"
  POSTGRES_PORT_SOURCE="local .env:POSTGRES_HOST_PORT"
else
  POSTGRES_PORT="${POSTGRES_PORT:-${POSTGRES_HOST_PORT:-5432}}"
  POSTGRES_PORT_SOURCE="environment/default"
fi

if [ -n "$POSTGRES_HOST_CONFIG" ]; then
  POSTGRES_LISTEN_HOST="$POSTGRES_HOST_CONFIG"
  POSTGRES_LISTEN_HOST_SOURCE="POSTGRES_HOST_CONFIG"
elif [ -n "$LOCAL_ENV_POSTGRES_HOST_CONFIG" ]; then
  POSTGRES_LISTEN_HOST="$LOCAL_ENV_POSTGRES_HOST_CONFIG"
  POSTGRES_LISTEN_HOST_SOURCE="local .env:POSTGRES_HOST_CONFIG"
elif [ -n "$POSTGRES_CONF_LISTEN_ADDRESSES" ]; then
  POSTGRES_LISTEN_HOST="$POSTGRES_CONF_LISTEN_ADDRESSES"
  POSTGRES_LISTEN_HOST_SOURCE="postgresql.conf:listen_addresses"
elif [ -n "$LOCAL_ENV_POSTGRES_LISTEN_HOST" ]; then
  POSTGRES_LISTEN_HOST="$LOCAL_ENV_POSTGRES_LISTEN_HOST"
  POSTGRES_LISTEN_HOST_SOURCE="local .env:POSTGRES_LISTEN_HOST"
elif [ -n "$LOCAL_ENV_POSTGRES_HOST" ]; then
  POSTGRES_LISTEN_HOST="$LOCAL_ENV_POSTGRES_HOST"
  POSTGRES_LISTEN_HOST_SOURCE="local .env:POSTGRES_HOST"
else
  POSTGRES_LISTEN_HOST="${POSTGRES_LISTEN_HOST:-${POSTGRES_HOST:-0.0.0.0}}"
  POSTGRES_LISTEN_HOST_SOURCE="environment/default"
fi

if [ -n "$LOCAL_ENV_POSTGRES_CONNECT_HOST" ]; then
  POSTGRES_CONNECT_HOST="$LOCAL_ENV_POSTGRES_CONNECT_HOST"
  POSTGRES_CONNECT_HOST_SOURCE="local .env:POSTGRES_CONNECT_HOST"
elif [ -n "${POSTGRES_CONNECT_HOST:-}" ]; then
  POSTGRES_CONNECT_HOST="$POSTGRES_CONNECT_HOST"
  POSTGRES_CONNECT_HOST_SOURCE="environment:POSTGRES_CONNECT_HOST"
else
  POSTGRES_CONNECT_HOST="$POSTGRES_LISTEN_HOST"
  POSTGRES_CONNECT_HOST_SOURCE="follow:POSTGRES_LISTEN_HOST"
fi

if [ "$POSTGRES_CONNECT_HOST" = "*" ] || [ "$POSTGRES_CONNECT_HOST" = "0.0.0.0" ]; then
  POSTGRES_CONNECT_HOST="127.0.0.1"
  POSTGRES_CONNECT_HOST_SOURCE="normalize(local-connect)"
fi

POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-}"
if [ -n "$POSTGRES_CONF_DATA_DIR" ]; then
  POSTGRES_DATA_DIR="$POSTGRES_CONF_DATA_DIR"
  POSTGRES_DATA_DIR_SOURCE="postgresql.conf:data_directory"
elif [ -n "$LOCAL_ENV_POSTGRES_DATA_DIR" ]; then
  POSTGRES_DATA_DIR="$LOCAL_ENV_POSTGRES_DATA_DIR"
  POSTGRES_DATA_DIR_SOURCE="local .env:POSTGRES_DATA_DIR"
else
  POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-}"
  POSTGRES_DATA_DIR_SOURCE="environment/default"
fi

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

check_line() {
  local ok="$1"
  local key="$2"
  local detail="$3"
  local advice="$4"

  if [ "$ok" = "1" ]; then
    echo "✅ $key: $detail"
  else
    echo "× $key: $detail"
    echo "   建议: $advice"
  fi
}

check_preflight_config() {
  local failed=0

  echo ""
  echo "启动前配置检查（仅检查，不启动服务）"
  echo ""

  if [ -f "$POSTGRES_CONF_FILE" ]; then
    check_line 1 "postgresql.conf" "已找到: $POSTGRES_CONF_FILE" ""
  else
    check_line 0 "postgresql.conf" "未找到: $POSTGRES_CONF_FILE" "在 ENV_ROOT_DIR 下提供 postgresql.conf，或在 $LOCAL_ENV_FILE 配置 POSTGRES_PORT/POSTGRES_DATA_DIR"
  fi

  if [ -f "$LOCAL_ENV_FILE" ]; then
    check_line 1 "local .env" "已找到: $LOCAL_ENV_FILE" ""
  else
    check_line 0 "local .env" "未找到: $LOCAL_ENV_FILE" "在脚本目录创建 .env，并至少配置 POSTGRES_PORT 与 POSTGRES_DATA_DIR"
  fi

  if echo "$POSTGRES_PORT" | grep -Eq '^[0-9]+$'; then
    check_line 1 "POSTGRES_PORT" "$POSTGRES_PORT (来源: $POSTGRES_PORT_SOURCE)" ""
  else
    check_line 0 "POSTGRES_PORT" "值无效: ${POSTGRES_PORT:-<empty>} (来源: $POSTGRES_PORT_SOURCE)" "将端口改为数字，例如 15432"
    failed=1
  fi

  if [ -n "$POSTGRES_LISTEN_HOST" ]; then
    check_line 1 "POSTGRES_LISTEN_HOST" "$POSTGRES_LISTEN_HOST (来源: $POSTGRES_LISTEN_HOST_SOURCE)" ""
  else
    check_line 0 "POSTGRES_LISTEN_HOST" "未配置" "在 postgresql.conf 配置 listen_addresses，或在 $LOCAL_ENV_FILE 配置 POSTGRES_HOST_CONFIG/POSTGRES_LISTEN_HOST"
    failed=1
  fi

  if [ -n "$POSTGRES_CONNECT_HOST" ]; then
    check_line 1 "POSTGRES_CONNECT_HOST" "$POSTGRES_CONNECT_HOST (来源: $POSTGRES_CONNECT_HOST_SOURCE)" ""
  else
    check_line 0 "POSTGRES_CONNECT_HOST" "未配置" "在 $LOCAL_ENV_FILE 配置 POSTGRES_CONNECT_HOST（例如 127.0.0.1）"
    failed=1
  fi

  if [ -n "$POSTGRES_DATA_DIR" ]; then
    if [ -d "$POSTGRES_DATA_DIR" ]; then
      check_line 1 "POSTGRES_DATA_DIR" "$POSTGRES_DATA_DIR (来源: $POSTGRES_DATA_DIR_SOURCE)" ""
    else
      check_line 0 "POSTGRES_DATA_DIR" "目录不存在: $POSTGRES_DATA_DIR (来源: $POSTGRES_DATA_DIR_SOURCE)" "先创建目录: mkdir -p '$POSTGRES_DATA_DIR'"
      failed=1
    fi
  else
    check_line 0 "POSTGRES_DATA_DIR" "未配置" "在 postgresql.conf 配置 data_directory，或在 $LOCAL_ENV_FILE 配置 POSTGRES_DATA_DIR"
    failed=1
  fi

  if [ -n "$POSTGRES_USER" ]; then
    check_line 1 "POSTGRES_USER" "$POSTGRES_USER" ""
  else
    check_line 0 "POSTGRES_USER" "未配置" "在 .env 中配置 POSTGRES_USER，例如 photo"
    failed=1
  fi

  if [ -n "$POSTGRES_DB" ]; then
    check_line 1 "POSTGRES_DB" "$POSTGRES_DB" ""
  else
    check_line 0 "POSTGRES_DB" "未配置" "在 .env 中配置 POSTGRES_DB，例如 photo"
    failed=1
  fi

  if [ -n "$INITDB_BIN" ] && [ -x "$INITDB_BIN" ]; then
    check_line 1 "INITDB" "$INITDB_BIN" ""
  else
    check_line 0 "INITDB" "未找到可执行 initdb" "安装 postgresql@17，或在 .env 配置 POSTGRES_BIN_DIR"
    failed=1
  fi

  if [ -n "$PG_CTL_BIN" ] && [ -x "$PG_CTL_BIN" ]; then
    check_line 1 "PG_CTL" "$PG_CTL_BIN" ""
  else
    check_line 0 "PG_CTL" "未找到可执行 pg_ctl" "安装 postgresql@17，或在 .env 配置 POSTGRES_BIN_DIR"
    failed=1
  fi

  if [ -n "$PG_ISREADY_BIN" ] && [ -x "$PG_ISREADY_BIN" ]; then
    check_line 1 "PG_ISREADY" "$PG_ISREADY_BIN" ""
  else
    check_line 0 "PG_ISREADY" "未找到可执行 pg_isready" "安装 postgresql@17，或在 .env 配置 POSTGRES_BIN_DIR"
    failed=1
  fi

  if [ "$failed" -eq 0 ]; then
    echo ""
    echo "✅ 配置检查通过，可以执行启动。"
    return 0
  fi

  echo ""
  echo "× 配置检查未通过，请按上面的建议修复后重试。"
  return 1
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
  "$PG_ISREADY_BIN" -h "$POSTGRES_CONNECT_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1
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
    -h "$POSTGRES_CONNECT_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d postgres \
    -tAc "SELECT 1 FROM pg_database WHERE datname = '$POSTGRES_DB'" \
    2>/dev/null || true)"

  if [ "$exists" = "1" ]; then
    return 0
  fi

  log_info "创建数据库: $POSTGRES_DB"
  "$CREATEDB_BIN" -h "$POSTGRES_CONNECT_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" "$POSTGRES_DB"
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

  log_info "启动 PostgreSQL (host=$POSTGRES_LISTEN_HOST, port=$POSTGRES_PORT)..."
  if ! "$PG_CTL_BIN" \
    -D "$POSTGRES_DATA_DIR" \
    -l "$(log_file postgres)" \
    -o "-p $POSTGRES_PORT -h $POSTGRES_LISTEN_HOST" \
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
  echo "用法: ./scripts/start-postgres.sh [start|stop|restart|check|help]"
  echo ""
  echo "命令:"
  echo "  start    启动 PostgreSQL（默认）"
  echo "  stop     停止当前 POSTGRES_DATA_DIR 对应的 PostgreSQL"
  echo "  restart  重启 PostgreSQL"
  echo "  check    检查启动前配置（不启动服务）"
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
  check)
    check_preflight_config
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
