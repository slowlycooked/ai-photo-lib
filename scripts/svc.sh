#!/usr/bin/env bash
# scripts/svc.sh — 统一服务管理脚本
# 用法: ./scripts/svc.sh {start|stop|restart|status} [服务名...]
#
# 服务名: postgres  redis  api  web  all（默认）
#
# 示例:
#   ./scripts/svc.sh start           # 启动全部
#   ./scripts/svc.sh start api web   # 只启动 api 和 web
#   ./scripts/svc.sh stop            # 停止全部
#   ./scripts/svc.sh restart api     # 重启 api
#   ./scripts/svc.sh status          # 查看全部状态

set -euo pipefail

# ── 路径常量 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_DIR="$ROOT/.run"       # PID / log 文件目录
LOG_DIR="$ROOT/.logs"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# ── 颜色 ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# ── 加载 .env ─────────────────────────────────────────────────────────────────
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
REDIS_HOST_PORT="${REDIS_HOST_PORT:-6379}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8082/v1}"
OPENAI_MODEL="${OPENAI_MODEL:-}"
OPENAI_VISION_MODEL="${OPENAI_VISION_MODEL:-}"
LLAMA_SERVER="${LLAMA_SERVER:-}"
LLAMA_MODEL="${LLAMA_MODEL:-}"
LLAMA_MMPROJ="${LLAMA_MMPROJ:-}"
LLAMA_PORT="${LLAMA_PORT:-8082}"
LLAMA_CTX="${LLAMA_CTX:-8192}"
LLAMA_MEDIA_PATH="${LLAMA_MEDIA_PATH:-${PHOTO_LIBRARY_PATH:-}}"

# ── 辅助函数 ──────────────────────────────────────────────────────────────────
log_info()    { echo -e "${CYAN}▶${RESET} $*"; }
log_ok()      { echo -e "${GREEN}✓${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
log_error()   { echo -e "${RED}✗${RESET} $*" >&2; }

pid_file()    { echo "$RUN_DIR/$1.pid"; }
log_file()    { echo "$LOG_DIR/$1.log"; }

is_running() {
  local name="$1"
  local pf; pf="$(pid_file "$name")"
  if [ -f "$pf" ]; then
    local pid; pid="$(cat "$pf")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    else
      rm -f "$pf"
    fi
  fi
  return 1
}

save_pid() { echo "$!" > "$(pid_file "$1")"; }

# ── Docker Compose 健康等待 ────────────────────────────────────────────────────
wait_healthy() {
  local svc="$1" max="${2:-30}" i=0
  log_info "等待 $svc 健康检查通过..."
  until docker compose -f "$ROOT/docker-compose.yml" ps "$svc" \
        | grep -q "healthy" 2>/dev/null; do
    sleep 2; i=$((i+2))
    if [ $i -ge $max ]; then
      log_error "$svc 在 ${max}s 内未健康，请检查日志: docker compose logs $svc"
      return 1
    fi
  done
  log_ok "$svc 已就绪"
}

# ────────────────────────────────────────────────────────────────────────────
# START 函数
# ────────────────────────────────────────────────────────────────────────────

start_postgres() {
  if docker compose -f "$ROOT/docker-compose.yml" ps postgres \
     | grep -q "healthy" 2>/dev/null; then
    log_ok "postgres 已在运行 (port $POSTGRES_HOST_PORT)"
    return 0
  fi
  log_info "启动 postgres (port $POSTGRES_HOST_PORT)..."
  cd "$ROOT"
  docker compose up -d postgres
  wait_healthy postgres 60
}

start_redis() {
  if docker compose -f "$ROOT/docker-compose.yml" ps redis \
     | grep -q "healthy" 2>/dev/null; then
    log_ok "redis 已在运行 (port $REDIS_HOST_PORT)"
    return 0
  fi
  log_info "启动 redis (port $REDIS_HOST_PORT)..."
  cd "$ROOT"
  docker compose up -d redis
  wait_healthy redis 30
}

start_api() {
  if is_running api; then
    log_ok "api 已在运行 (PID $(cat "$(pid_file api)"), port $API_PORT)"
    return 0
  fi

  log_info "运行数据库迁移..."
  cd "$ROOT/apps/api"
  [ -d ".venv" ] && source .venv/bin/activate
  alembic upgrade head

  log_info "启动 API (uvicorn :$API_PORT)..."
  cd "$ROOT/apps/api"
  [ -d ".venv" ] && source .venv/bin/activate
  nohup uvicorn app.main:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --reload \
    > "$(log_file api)" 2>&1 &
  save_pid api
  sleep 1
  if is_running api; then
    log_ok "api 已启动 (PID $(cat "$(pid_file api)"), log: .logs/api.log)"
  else
    log_error "api 启动失败，请查看 .logs/api.log"
    return 1
  fi
}

start_web() {
  if is_running web; then
    log_ok "web 已在运行 (PID $(cat "$(pid_file web)"), port $WEB_PORT)"
    return 0
  fi

  log_info "启动 Web Dev Server (port $WEB_PORT)..."
  cd "$ROOT/apps/web"
  if [ ! -d "node_modules" ]; then
    log_info "安装前端依赖 (npm install)..."
    npm install --silent
  fi
  nohup npm run dev -- --port "$WEB_PORT" \
    > "$(log_file web)" 2>&1 &
  save_pid web
  sleep 2
  if is_running web; then
    log_ok "web 已启动 (PID $(cat "$(pid_file web)"), log: .logs/web.log)"
  else
    log_error "web 启动失败，请查看 .logs/web.log"
    return 1
  fi
}

# ────────────────────────────────────────────────────────────────────────────
# STOP 函数
# ────────────────────────────────────────────────────────────────────────────

stop_api() {
  if is_running api; then
    local pid; pid="$(cat "$(pid_file api)")"
    log_info "停止 api (PID $pid)..."
    kill "$pid" 2>/dev/null && rm -f "$(pid_file api)"
    log_ok "api 已停止"
  else
    log_warn "api 未在运行"
  fi
}

stop_web() {
  if is_running web; then
    local pid; pid="$(cat "$(pid_file web)")"
    log_info "停止 web (PID $pid)..."
    # npm run dev 会 fork 子进程，需要杀整个进程组
    kill -- -"$(ps -o pgid= -p "$pid" | tr -d ' ')" 2>/dev/null \
      || kill "$pid" 2>/dev/null
    rm -f "$(pid_file web)"
    log_ok "web 已停止"
  else
    log_warn "web 未在运行"
  fi
}

stop_postgres() {
  log_info "停止 postgres..."
  cd "$ROOT"
  docker compose stop postgres
  log_ok "postgres 已停止"
}

stop_redis() {
  log_info "停止 redis..."
  cd "$ROOT"
  docker compose stop redis
  log_ok "redis 已停止"
}

start_worker() {
  if is_running worker; then
    log_ok "worker 已在运行 (PID $(cat "$(pid_file worker)")"
    return 0
  fi

  log_info "启动 AI Worker..."
  cd "$ROOT/apps/api"
  [ -d ".venv" ] && source .venv/bin/activate
  cd "$ROOT/apps/worker"
  nohup python main.py \
    > "$(log_file worker)" 2>&1 &
  save_pid worker
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
    local pid; pid="$(cat "$(pid_file worker)")"
    log_info "停止 worker (PID $pid)..."
    kill "$pid" 2>/dev/null && rm -f "$(pid_file worker)"
    log_ok "worker 已停止"
  else
    log_warn "worker 未在运行"
  fi
}

start_ai() {
  if is_running ai; then
    log_ok "llama-server 已在运行 (PID $(cat "$(pid_file ai)"), port $LLAMA_PORT)"
    return 0
  fi

  if [ -z "$LLAMA_SERVER" ] || [ -z "$LLAMA_MODEL" ]; then
    log_warn "LLAMA_SERVER / LLAMA_MODEL 未在 .env 中配置，跳过启动"
    return 0
  fi

  local args=(
    "$LLAMA_SERVER"
    -m "$LLAMA_MODEL"
    --host 127.0.0.1
    --port "$LLAMA_PORT"
    -c "$LLAMA_CTX"
  )
  [ -n "$LLAMA_MMPROJ" ]     && args+=(--mmproj "$LLAMA_MMPROJ")
  [ -n "$LLAMA_MEDIA_PATH" ] && args+=(--media-path "$LLAMA_MEDIA_PATH")

  log_info "启动 llama-server (port $LLAMA_PORT, media-path=${LLAMA_MEDIA_PATH:-未设置})..."
  nohup "${args[@]}" > "$(log_file ai)" 2>&1 &
  save_pid ai
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
    local pid; pid="$(cat "$(pid_file ai)")"
    log_info "停止 llama-server (PID $pid)..."
    kill "$pid" 2>/dev/null && rm -f "$(pid_file ai)"
    log_ok "llama-server 已停止"
  else
    log_warn "llama-server 未在运行 (由 svc.sh 管理的实例)"
  fi
}

# ────────────────────────────────────────────────────────────────────────────
# STATUS 函数
# ────────────────────────────────────────────────────────────────────────────

status_process() {
  local name="$1" label="$2" port="$3"
  if is_running "$name"; then
    local pid; pid="$(cat "$(pid_file "$name")")"
    printf "  ${GREEN}%-10s${RESET} ${GREEN}running${RESET}  PID=%-6s port=%s  log=%s\n" \
      "$label" "$pid" "$port" ".logs/$name.log"
  else
    printf "  ${RED}%-10s${RESET} ${RED}stopped${RESET}\n" "$label"
  fi
}

status_docker() {
  local svc="$1" label="$2" port="$3"
  local state
  state=$(docker compose -f "$ROOT/docker-compose.yml" ps --format json "$svc" 2>/dev/null \
          | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Health','') or d.get('State','unknown'))" \
          2>/dev/null || echo "unknown")
  if [[ "$state" == "healthy" ]]; then
    printf "  ${GREEN}%-10s${RESET} ${GREEN}%-8s${RESET} port=%s\n" "$label" "$state" "$port"
  elif [[ "$state" == "running" ]]; then
    printf "  ${YELLOW}%-10s${RESET} ${YELLOW}%-8s${RESET} port=%s  (health check pending)\n" "$label" "$state" "$port"
  else
    printf "  ${RED}%-10s${RESET} ${RED}%-8s${RESET}\n" "$label" "$state"
  fi
}

status_ai() {
  # 从 OPENAI_BASE_URL 提取 host:port 用于显示
  local url="$OPENAI_BASE_URL"
  local host_port
  host_port=$(echo "$url" | sed -E 's|https?://([^/]+).*|\1|')

  local models_url="${url%/}/models"
  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    --connect-timeout 2 --max-time 4 \
    -H "Authorization: Bearer ${OPENAI_API_KEY:-sk-local}" \
    "$models_url" 2>/dev/null || echo "000")

  local model_info=""
  [ -n "$OPENAI_MODEL" ] && model_info=" model=$OPENAI_MODEL"

  if [[ "$http_code" == "200" ]]; then
    printf "  ${GREEN}%-10s${RESET} ${GREEN}%-8s${RESET} %s%s\n" \
      "AI" "online" "$host_port" "$model_info"
  elif [[ "$http_code" == "000" ]]; then
    printf "  ${RED}%-10s${RESET} ${RED}%-8s${RESET} %s  (连接失败)\n" \
      "AI" "offline" "$host_port"
  else
    printf "  ${YELLOW}%-10s${RESET} ${YELLOW}%-8s${RESET} %s  (HTTP %s)\n" \
      "AI" "unknown" "$host_port" "$http_code"
  fi
}

show_status() {
  echo ""
  echo -e "${BOLD}── 服务状态 ─────────────────────────────────────────${RESET}"
  status_docker  "postgres" "PostgreSQL" "$POSTGRES_HOST_PORT"
  status_docker  "redis"    "Redis"      "$REDIS_HOST_PORT"
  status_process "api"      "API"        "$API_PORT"
  status_process "web"      "Web"        "$WEB_PORT"
  status_process "worker"   "Worker"     "-"
  status_process "ai"       "llama-srv"  "$LLAMA_PORT"
  status_ai
  echo -e "${BOLD}─────────────────────────────────────────────────────${RESET}"
  echo ""
}

# ────────────────────────────────────────────────────────────────────────────
# 批量操作分发
# ────────────────────────────────────────────────────────────────────────────

resolve_services() {
  # 如果没有指定服务，默认操作全部
  if [ $# -eq 0 ]; then
    echo "postgres redis ai api worker web"
  else
    echo "$@"
  fi
}

do_start() {
  local services; services="$(resolve_services "$@")"
  echo ""
  log_info "启动服务: $services"
  echo ""
  for svc in $services; do
    case "$svc" in
      postgres) start_postgres ;;
      redis)    start_redis ;;
      api)      start_api ;;
      worker)   start_worker ;;
      ai)       start_ai ;;
      web)      start_web ;;
      all)      start_postgres; start_redis; start_ai; start_api; start_worker; start_web ;;
      *)        log_error "未知服务: $svc"; exit 1 ;;
    esac
  done
  echo ""
  show_status
}

do_stop() {
  local services; services="$(resolve_services "$@")"
  # 停止顺序：先应用层，再基础设施
  local ordered=""
  for s in web worker api ai redis postgres; do
    if echo "$services" | grep -qw "$s"; then
      ordered="$ordered $s"
    fi
  done
  echo ""
  log_info "停止服务: $ordered"
  echo ""
  for svc in $ordered; do
    case "$svc" in
      postgres) stop_postgres ;;
      redis)    stop_redis ;;
      api)      stop_api ;;
      worker)   stop_worker ;;
      ai)       stop_ai ;;
      web)      stop_web ;;
      all)      stop_web; stop_worker; stop_ai; stop_api; stop_redis; stop_postgres ;;
      *)        log_error "未知服务: $svc"; exit 1 ;;
    esac
  done
  echo ""
}

do_restart() {
  echo ""
  log_info "重启服务: $*"
  do_stop "$@"
  do_start "$@"
}

# ────────────────────────────────────────────────────────────────────────────
# 入口
# ────────────────────────────────────────────────────────────────────────────

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
    echo "  logs    <服务>      实时追踪日志（api / web）"
    echo ""
    echo -e "${BOLD}服务名:${RESET}"
    echo "  postgres  — PostgreSQL    (Docker)"
    echo "  redis     — Redis          (Docker)"
    echo "  ai        — llama-server  (本地进程, OPENAI_BASE_URL, port LLAMA_PORT)"
    echo "  api       — FastAPI        (uvicorn, 本地进程, port API_PORT)"
    echo "  worker    — AI Worker      (Python 轮询 ai_jobs 表)"
    echo "  web       — React          (vite dev server, port WEB_PORT)"
    echo ""
    echo -e "${BOLD}示例:${RESET}"
    echo "  ./scripts/svc.sh start"
    echo "  ./scripts/svc.sh start api web"
    echo "  ./scripts/svc.sh restart api"
    echo "  ./scripts/svc.sh stop"
    echo "  ./scripts/svc.sh logs web"
    echo ""
    ;;
  *)
    log_error "未知命令: $COMMAND"
    echo "运行 './scripts/svc.sh help' 查看帮助"
    exit 1
    ;;
esac
