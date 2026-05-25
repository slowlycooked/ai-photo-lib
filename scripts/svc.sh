#!/usr/bin/env bash
# scripts/svc.sh — macOS native service manager
# 用法: ./scripts/svc.sh {start|stop|restart|status|logs} [服务名...]
#
# 服务名: postgres ai embed api worker web all（默认全部）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/.logs"

mkdir -p "$RUN_DIR" "$LOG_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log_info()  { echo -e "${CYAN}>${RESET} $*"; }
log_ok()    { echo -e "${GREEN}OK${RESET} $*"; }
log_warn()  { echo -e "${YELLOW}WARN${RESET} $*"; }
log_error() { echo -e "${RED}ERR${RESET} $*" >&2; }

ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

DEPLOY_PROFILE="${DEPLOY_PROFILE:-dev}"

POSTGRES_USER="${POSTGRES_USER:-photo}"
POSTGRES_DB="${POSTGRES_DB:-photo}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-photo}"
POSTGRES_PORT="${POSTGRES_PORT:-${POSTGRES_HOST_PORT:-5432}}"
POSTGRES_BIN_DIR="${POSTGRES_BIN_DIR:-}"
POSTGRES_DATA_DIR="${POSTGRES_DATA_DIR:-}"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
API_RELOAD="${API_RELOAD:-0}"

WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-8088}"
WEB_MODE="${WEB_MODE:-$([ "$DEPLOY_PROFILE" = "runtime" ] && echo preview || echo dev)}"

LLAMA_SERVER="${LLAMA_SERVER:-$(command -v llama-server 2>/dev/null || true)}"
LLAMA_MODEL="${LLAMA_MODEL:-}"
LLAMA_MMPROJ="${LLAMA_MMPROJ:-}"
LLAMA_PORT="${LLAMA_PORT:-8082}"
LLAMA_CTX="${LLAMA_CTX:-8192}"
LLAMA_CACHE_RAM="${LLAMA_CACHE_RAM:-0}"
LLAMA_MEDIA_PATH="${LLAMA_MEDIA_PATH:-${PHOTO_LIBRARY_PATH:-}}"
LLAMA_STOP_TIMEOUT="${LLAMA_STOP_TIMEOUT:-15}"

EMBED_SERVER="${EMBED_SERVER:-${LLAMA_SERVER:-}}"
EMBED_MODEL="${EMBED_MODEL:-}"
EMBED_PORT="${EMBED_PORT:-8083}"
EMBED_CTX="${EMBED_CTX:-8192}"
EMBED_UB="${EMBED_UB:-8192}"
EMBED_STOP_TIMEOUT="${EMBED_STOP_TIMEOUT:-15}"

pid_file() { echo "$RUN_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

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

api_python_bin() {
  local py_bin="$ROOT/apps/api/.venv/bin/python"
  if [ -x "$py_bin" ]; then
    echo "$py_bin"
    return 0
  fi

  log_error "未找到 API Python 解释器: $py_bin"
  log_error "请先执行 ./scripts/bootstrap-macos.sh 或在 apps/api 下创建 .venv 并安装依赖"
  return 1
}

service_port() {
  case "$1" in
    postgres) echo "$POSTGRES_PORT" ;;
    api)      echo "$API_PORT" ;;
    web)      echo "$WEB_PORT" ;;
    ai)       echo "$LLAMA_PORT" ;;
    embed)    echo "$EMBED_PORT" ;;
    *)        echo "" ;;
  esac
}

service_cmd_pattern() {
  case "$1" in
    postgres) echo 'postgres .* -D |postmaster' ;;
    api)      echo 'ai-photo-api|uvicorn .*(app\.main:app|main:app)' ;;
    web)      echo 'ai-photo-web|vite|npm run (dev|preview)' ;;
    ai)       echo 'ai-photo-llama|llama-server' ;;
    embed)    echo 'ai-photo-embed|llama-server' ;;
    worker)   echo 'ai-photo-worker|python(3)? .*main\.py' ;;
    *)        echo '' ;;
  esac
}

get_listen_pid_by_port() {
  local port="$1"
  { lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true; } | awk 'NR==2{print $2}'
}

save_pid() {
  echo "$1" > "$(pid_file "$2")"
}

save_bg_pid() {
  save_pid "$!" "$1"
}

run_named_process() {
  local proc_name="$1"
  shift
  nohup "$ROOT/scripts/ai-photo-runner.sh" "$proc_name" "$@"
}

find_prefixed_pids() {
  local pattern="$1"
  (ps ax -o pid=,command= 2>/dev/null || true) \
    | grep -E "$pattern" \
    | grep -v grep \
    | awk '{print $1}'
}

kill_prefixed_processes() {
  local pattern="$1"
  local label="$2"
  local pids=""
  pids="$(find_prefixed_pids "$pattern" | tr '\n' ' ' | xargs 2>/dev/null || true)"
  if [ -z "$pids" ]; then
    return 0
  fi

  log_warn "发现残留 $label 进程，执行清理: $pids"
  kill -TERM $pids 2>/dev/null || true
  sleep 1

  local remain=""
  remain="$(find_prefixed_pids "$pattern" | tr '\n' ' ' | xargs 2>/dev/null || true)"
  if [ -n "$remain" ]; then
    kill -KILL $remain 2>/dev/null || true
  fi
}

kill_listener_by_service_port() {
  local name="$1"
  local port=""
  port="$(service_port "$name")"
  [ -z "$port" ] && return 0

  local pid=""
  pid="$(get_listen_pid_by_port "$port")"
  [ -z "$pid" ] && return 0

  local cmd=""
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  local pattern=""
  pattern="$(service_cmd_pattern "$name")"
  if [ -n "$pattern" ] && ! echo "$cmd" | grep -qiE "$pattern"; then
    return 0
  fi

  log_warn "检测到 $name 仍监听端口 $port (PID $pid)，执行清理"
  kill -TERM "$pid" 2>/dev/null || true
  sleep 1
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
}

sync_pid_from_port() {
  local name="$1"
  local port=""
  port="$(service_port "$name")"
  [ -z "$port" ] && return 1

  local listen_pid=""
  listen_pid="$(get_listen_pid_by_port "$port")"
  [ -z "$listen_pid" ] && return 1

  local cmd=""
  cmd="$(ps -p "$listen_pid" -o command= 2>/dev/null || true)"
  local pattern=""
  pattern="$(service_cmd_pattern "$name")"
  if [ -n "$pattern" ] && ! echo "$cmd" | grep -qiE "$pattern"; then
    return 1
  fi

  save_pid "$listen_pid" "$name"
  return 0
}

is_running() {
  local name="$1"
  local pf
  pf="$(pid_file "$name")"

  if [ "$name" != "worker" ] && sync_pid_from_port "$name"; then
    return 0
  fi

  if [ -f "$pf" ]; then
    local pid
    pid="$(cat "$pf")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    rm -f "$pf"
  fi

  if [ "$name" = "worker" ]; then
    local pids=""
    pids="$(find_prefixed_pids '(^| )ai-photo-worker( |$)' | tr '\n' ' ' | xargs 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      save_pid "${pids%% *}" worker
      return 0
    fi
  fi

  return 1
}

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
  require_postgres_tools || return 1

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
    log_warn "检测到外部 PostgreSQL 正在端口 $POSTGRES_PORT 运行；未执行停止。"
    return 0
  fi

  log_warn "postgres 未在运行"
}

run_migrations() {
  local py_bin
  py_bin="$(api_python_bin)"

  cd "$ROOT/apps/api"
  "$py_bin" stamp_migrations.py >/dev/null 2>&1 || true
  "$py_bin" -m alembic upgrade head
}

start_api() {
  if is_running api; then
    log_ok "api 已在运行 (PID $(cat "$(pid_file api)"), port $API_PORT)"
    return 0
  fi

  if ! postgres_is_ready; then
    start_postgres
  fi

  log_info "运行数据库迁移..."
  run_migrations

  local py_bin
  py_bin="$(api_python_bin)"

  log_info "启动 API (host=$API_HOST, port=$API_PORT, reload=$API_RELOAD)..."
  cd "$ROOT/apps/api"
  local uvicorn_args=(
    -m uvicorn
    app.main:app
    --host "$API_HOST"
    --port "$API_PORT"
    --no-access-log
  )
  if [ "$API_RELOAD" = "1" ] || [ "$API_RELOAD" = "true" ]; then
    uvicorn_args+=(--reload)
  fi

  run_named_process "ai-photo-api" "$py_bin" "${uvicorn_args[@]}" > "$(log_file api)" 2>&1 &
  save_bg_pid api
  sleep 2

  if is_running api && curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    log_ok "api 已启动 (PID $(cat "$(pid_file api)"), log: .logs/api.log)"
  else
    log_error "api 启动失败，请查看 .logs/api.log"
    return 1
  fi
}

stop_api() {
  if is_running api; then
    local pid
    pid="$(cat "$(pid_file api)")"
    log_info "停止 api (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    rm -f "$(pid_file api)"
    log_ok "api 已停止"
  else
    log_warn "api 未在运行"
  fi
  kill_prefixed_processes '(^| )ai-photo-api( |$)' 'api'
  kill_listener_by_service_port api
}

start_web() {
  if is_running web; then
    log_ok "web 已在运行 (PID $(cat "$(pid_file web)"), port $WEB_PORT)"
    return 0
  fi

  if ! command -v npm >/dev/null 2>&1; then
    log_error "未找到 npm，请先安装 Node.js 20+"
    return 1
  fi

  cd "$ROOT/apps/web"
  if [ ! -d "node_modules" ]; then
    log_info "安装前端依赖..."
    npm install --silent
  fi

  case "$WEB_MODE" in
    dev)
      log_info "启动 Web 开发服务 (host=$WEB_HOST, port=$WEB_PORT)..."
      run_named_process "ai-photo-web" npm run dev -- --host "$WEB_HOST" --port "$WEB_PORT" > "$(log_file web)" 2>&1 &
      ;;
    preview)
      log_info "构建前端并启动 Preview 服务 (host=$WEB_HOST, port=$WEB_PORT)..."
      run_named_process "ai-photo-web" sh -c "cd '$ROOT/apps/web' && npm run build >/dev/null && npm run preview -- --host '$WEB_HOST' --port '$WEB_PORT'" > "$(log_file web)" 2>&1 &
      ;;
    *)
      log_error "不支持的 WEB_MODE: $WEB_MODE（可选: dev / preview）"
      return 1
      ;;
  esac

  save_bg_pid web
  sleep 3
  if is_running web; then
    log_ok "web 已启动 (PID $(cat "$(pid_file web)"), log: .logs/web.log)"
  else
    log_error "web 启动失败，请查看 .logs/web.log"
    return 1
  fi
}

stop_web() {
  if is_running web; then
    local pid
    pid="$(cat "$(pid_file web)")"
    log_info "停止 web (PID $pid)..."
    kill -- -"$(ps -o pgid= -p "$pid" | tr -d ' ')" 2>/dev/null || kill "$pid" 2>/dev/null || true
    rm -f "$(pid_file web)"
    log_ok "web 已停止"
  else
    log_warn "web 未在运行"
  fi
  kill_prefixed_processes '(^| )ai-photo-web( |$)' 'web'
  kill_listener_by_service_port web
}

start_worker() {
  if is_running worker; then
    log_ok "worker 已在运行 (PID $(cat "$(pid_file worker)"))"
    return 0
  fi

  local py_bin
  py_bin="$(api_python_bin)"

  log_info "启动 AI Worker..."
  cd "$ROOT/apps/worker"
  run_named_process "ai-photo-worker" "$py_bin" main.py > "$(log_file worker)" 2>&1 &
  save_bg_pid worker
  sleep 1

  if is_running worker; then
    log_ok "worker 已启动 (PID $(cat "$(pid_file worker)"), log: .logs/worker.log)"
  else
    log_error "worker 启动失败，请查看 .logs/worker.log"
    return 1
  fi
}

stop_worker() {
  if is_running worker; then
    local pid
    pid="$(cat "$(pid_file worker)")"
    log_info "停止 worker (PID $pid)..."
    kill "$pid" 2>/dev/null || true
    rm -f "$(pid_file worker)"
    log_ok "worker 已停止"
  else
    log_warn "worker 未在运行"
  fi
  kill_prefixed_processes '(^| )ai-photo-worker( |$)' 'worker'
}

start_ai() {
  if is_running ai; then
    log_ok "llama-server 已在运行 (PID $(cat "$(pid_file ai)"), port $LLAMA_PORT)"
    return 0
  fi

  local occupied_pid=""
  occupied_pid="$(get_listen_pid_by_port "$LLAMA_PORT")"
  if [ -n "$occupied_pid" ]; then
    local occupied_cmd=""
    occupied_cmd="$(ps -p "$occupied_pid" -o command= 2>/dev/null || true)"
    log_error "端口 $LLAMA_PORT 已被占用 (PID $occupied_pid): $occupied_cmd"
    return 1
  fi

  if [ -z "$LLAMA_SERVER" ] || [ -z "$LLAMA_MODEL" ]; then
    log_warn "LLAMA_SERVER / LLAMA_MODEL 未配置，跳过启动"
    return 0
  fi

  local args=(
    "$LLAMA_SERVER"
    -m "$LLAMA_MODEL"
    --host 127.0.0.1
    --port "$LLAMA_PORT"
    -c "$LLAMA_CTX"
    --cache-ram "$LLAMA_CACHE_RAM"
  )
  [ -n "$LLAMA_MMPROJ" ] && args+=(--mmproj "$LLAMA_MMPROJ")
  [ -n "$LLAMA_MEDIA_PATH" ] && args+=(--media-path "$LLAMA_MEDIA_PATH")

  log_info "启动 llama-server (port $LLAMA_PORT)..."
  run_named_process "ai-photo-llama" "${args[@]}" > "$(log_file ai)" 2>&1 &
  save_bg_pid ai
  sleep 2

  if is_running ai; then
    log_ok "llama-server 已启动 (PID $(cat "$(pid_file ai)"), log: .logs/ai.log)"
  else
    log_error "llama-server 启动失败，请查看 .logs/ai.log"
    return 1
  fi
}

stop_ai() {
  if is_running ai; then
    local pid
    pid="$(cat "$(pid_file ai)")"
    local waited=0

    log_info "停止 llama-server (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
      if [ "$waited" -ge "$LLAMA_STOP_TIMEOUT" ]; then
        kill -KILL "$pid" 2>/dev/null || true
        break
      fi
      sleep 1
      waited=$((waited + 1))
    done
    rm -f "$(pid_file ai)"
    log_ok "llama-server 已停止"
  else
    log_warn "llama-server 未在运行"
  fi
  kill_prefixed_processes '(^| )ai-photo-llama( |$)' 'llama-server'
  kill_listener_by_service_port ai
}

start_embed() {
  if is_running embed; then
    log_ok "llama-embed 已在运行 (PID $(cat "$(pid_file embed)"), port $EMBED_PORT)"
    return 0
  fi

  local occupied_pid=""
  occupied_pid="$(get_listen_pid_by_port "$EMBED_PORT")"
  if [ -n "$occupied_pid" ]; then
    local occupied_cmd=""
    occupied_cmd="$(ps -p "$occupied_pid" -o command= 2>/dev/null || true)"
    log_error "端口 $EMBED_PORT 已被占用 (PID $occupied_pid): $occupied_cmd"
    return 1
  fi

  if [ -z "$EMBED_SERVER" ] || [ -z "$EMBED_MODEL" ]; then
    log_warn "EMBED_SERVER / EMBED_MODEL 未配置，跳过启动"
    return 0
  fi

  local args=(
    "$EMBED_SERVER"
    -m "$EMBED_MODEL"
    --host 127.0.0.1
    --port "$EMBED_PORT"
    --embedding
    --pooling last
    -c "$EMBED_CTX"
    -ub "$EMBED_UB"
  )

  log_info "启动 llama-embed (port $EMBED_PORT)..."
  run_named_process "ai-photo-embed" "${args[@]}" > "$(log_file embed)" 2>&1 &
  save_bg_pid embed
  sleep 2

  if is_running embed; then
    log_ok "llama-embed 已启动 (PID $(cat "$(pid_file embed)"), log: .logs/embed.log)"
  else
    log_error "llama-embed 启动失败，请查看 .logs/embed.log"
    return 1
  fi
}

stop_embed() {
  if is_running embed; then
    local pid
    pid="$(cat "$(pid_file embed)")"
    local waited=0

    log_info "停止 llama-embed (PID $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    while kill -0 "$pid" 2>/dev/null; do
      if [ "$waited" -ge "$EMBED_STOP_TIMEOUT" ]; then
        kill -KILL "$pid" 2>/dev/null || true
        break
      fi
      sleep 1
      waited=$((waited + 1))
    done
    rm -f "$(pid_file embed)"
    log_ok "llama-embed 已停止"
  else
    log_warn "llama-embed 未在运行"
  fi
  kill_prefixed_processes '(^| )ai-photo-embed( |$)' 'llama-embed'
  kill_listener_by_service_port embed
}

status_process() {
  local name="$1"
  local label="$2"
  local port="$3"
  if is_running "$name"; then
    printf "  ${GREEN}%-10s${RESET} ${GREEN}running${RESET}  PID=%-6s port=%s  log=%s\n" \
      "$label" "$(cat "$(pid_file "$name")")" "$port" ".logs/$name.log"
  else
    printf "  ${RED}%-10s${RESET} ${RED}stopped${RESET}\n" "$label"
  fi
}

status_postgres() {
  local pg_pid=""
  pg_pid="$(postgres_pid_from_data_dir)"
  if postgres_is_ready; then
    if [ -n "$pg_pid" ] && kill -0 "$pg_pid" 2>/dev/null; then
      printf "  ${GREEN}%-10s${RESET} ${GREEN}running${RESET}  PID=%-6s port=%s  data=%s\n" \
        "PostgreSQL" "$pg_pid" "$POSTGRES_PORT" "$POSTGRES_DATA_DIR"
    else
      local listen_pid=""
      listen_pid="$(get_listen_pid_by_port "$POSTGRES_PORT")"
      printf "  ${YELLOW}%-10s${RESET} ${YELLOW}external${RESET} PID=%-6s port=%s\n" \
        "PostgreSQL" "${listen_pid:-?}" "$POSTGRES_PORT"
    fi
  else
    printf "  ${RED}%-10s${RESET} ${RED}stopped${RESET}\n" "PostgreSQL"
  fi
}

status_ai() {
  local url="${OPENAI_BASE_URL:-http://127.0.0.1:${LLAMA_PORT}/v1}"
  local models_url="${url%/}/models"
  local host_port
  host_port="$(echo "$url" | sed -E 's|https?://([^/]+).*|\1|')"

  local http_code
  http_code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 4 "$models_url" 2>/dev/null || true)"
  if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
    http_code="000"
  fi

  if [ "$http_code" = "200" ]; then
    printf "  ${GREEN}%-10s${RESET} ${GREEN}online${RESET}   %s\n" "AI" "$host_port"
  elif [ "$http_code" = "000" ]; then
    printf "  ${RED}%-10s${RESET} ${RED}offline${RESET}  %s\n" "AI" "$host_port"
  else
    printf "  ${YELLOW}%-10s${RESET} ${YELLOW}unknown${RESET}  %s (HTTP %s)\n" "AI" "$host_port" "$http_code"
  fi
}

status_embed() {
  local url="${EMBEDDING_BASE_URL:-http://127.0.0.1:${EMBED_PORT}/v1}/models"
  local http_code
  http_code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 4 "$url" 2>/dev/null || true)"
  if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
    http_code="000"
  fi

  if [ "$http_code" = "200" ]; then
    printf "  ${GREEN}%-10s${RESET} ${GREEN}online${RESET}   port=%s\n" "Embed" "$EMBED_PORT"
  elif [ "$http_code" = "000" ]; then
    printf "  ${RED}%-10s${RESET} ${RED}offline${RESET}  port=%s\n" "Embed" "$EMBED_PORT"
  else
    printf "  ${YELLOW}%-10s${RESET} ${YELLOW}unknown${RESET}  port=%s (HTTP %s)\n" "Embed" "$EMBED_PORT" "$http_code"
  fi
}

show_status() {
  echo ""
  echo -e "${BOLD}-- 服务状态 (${DEPLOY_PROFILE}) --${RESET}"
  status_postgres
  status_process "api" "API" "$API_PORT"
  status_process "web" "Web" "$WEB_PORT"
  status_process "worker" "Worker" "-"
  status_process "ai" "llama-srv" "$LLAMA_PORT"
  status_ai
  status_process "embed" "llama-emb" "$EMBED_PORT"
  status_embed
  echo ""
}

resolve_services() {
  if [ "$#" -eq 0 ]; then
    echo "postgres ai embed api worker web"
  else
    echo "$@"
  fi
}

do_start() {
  local services
  services="$(resolve_services "$@")"
  echo ""
  log_info "启动服务: $services"
  echo ""

  for svc in $services; do
    case "$svc" in
      postgres) start_postgres ;;
      ai)       start_ai ;;
      embed)    start_embed ;;
      api)      start_api ;;
      worker)   start_worker ;;
      web)      start_web ;;
      all)      start_postgres; start_ai; start_embed; start_api; start_worker; start_web ;;
      *)        log_error "未知服务: $svc"; exit 1 ;;
    esac
  done

  show_status
}

do_stop() {
  local services
  services="$(resolve_services "$@")"
  local ordered=""

  for s in web worker api embed ai postgres; do
    if echo "$services" | grep -qw "$s"; then
      ordered="$ordered $s"
    fi
  done

  echo ""
  log_info "停止服务:$ordered"
  echo ""

  for svc in $ordered; do
    case "$svc" in
      postgres) stop_postgres ;;
      ai)       stop_ai ;;
      embed)    stop_embed ;;
      api)      stop_api ;;
      worker)   stop_worker ;;
      web)      stop_web ;;
      all)      stop_web; stop_worker; stop_api; stop_embed; stop_ai; stop_postgres ;;
      *)        log_error "未知服务: $svc"; exit 1 ;;
    esac
  done
}

do_restart() {
  echo ""
  log_info "重启服务: $*"
  do_stop "$@"
  do_start "$@"
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
  start)   do_start "$@" ;;
  stop)    do_stop "$@" ;;
  restart) do_restart "$@" ;;
  status)  show_status ;;
  logs)
    SVC="${1:-api}"
    LOG="$(log_file "$SVC")"
    if [ -f "$LOG" ]; then
      tail -f "$LOG"
    else
      log_error "日志文件不存在: $LOG"
      exit 1
    fi
    ;;
  help|--help|-h)
    echo ""
    echo -e "${BOLD}用法:${RESET} ./scripts/svc.sh <命令> [服务...]"
    echo ""
    echo -e "${BOLD}命令:${RESET}"
    echo "  start   [服务...]   启动服务（默认: 全部）"
    echo "  stop    [服务...]   停止服务（默认: 全部）"
    echo "  restart [服务...]   重启服务（默认: 全部）"
    echo "  status              查看所有服务状态"
    echo "  logs    <服务>      实时追踪日志"
    echo ""
    echo -e "${BOLD}服务名:${RESET}"
    echo "  postgres  — PostgreSQL（本地进程，数据目录见 POSTGRES_DATA_DIR）"
    echo "  ai        — llama-server"
    echo "  embed     — llama embedding server"
    echo "  api       — FastAPI / uvicorn"
    echo "  worker    — AI Worker"
    echo "  web       — Vite（WEB_MODE=dev|preview）"
    echo ""
    echo -e "${BOLD}部署角色:${RESET}"
    echo "  DEPLOY_PROFILE=dev      MacBook 开发机默认：稳定 API + Web dev server"
    echo "  DEPLOY_PROFILE=runtime  Mac mini 运行机默认：稳定 API + Web preview"
    echo ""
    echo -e "${BOLD}示例:${RESET}"
    echo "  ./scripts/svc.sh start"
    echo "  ./scripts/svc.sh start postgres api web"
    echo "  DEPLOY_PROFILE=runtime ./scripts/svc.sh start"
    echo "  ./scripts/svc.sh logs postgres"
    echo ""
    ;;
  *)
    log_error "未知命令: $COMMAND"
    echo "运行 './scripts/svc.sh help' 查看帮助"
    exit 1
    ;;
esac
