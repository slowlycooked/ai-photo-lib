#!/usr/bin/env bash
# scripts/reset-dev.sh — 开发调试专用：清空数据库 + 缩略图
#
# 可选模式（默认全部清空）:
#   --db-only      只重置数据库（alembic downgrade → upgrade）
#   --thumbs       同时删除缩略图目录
#   --yes / -y     跳过确认提示（CI / 脚本调用时使用）
#
# 示例:
#   ./scripts/reset-dev.sh
#   ./scripts/reset-dev.sh --db-only
#   ./scripts/reset-dev.sh --thumbs --yes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 颜色 ─────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log_info()  { echo -e "${CYAN}▶${RESET} $*"; }
log_ok()    { echo -e "${GREEN}✓${RESET} $*"; }
log_warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
log_error() { echo -e "${RED}✗${RESET} $*" >&2; }
log_sep()   { echo -e "${BOLD}─────────────────────────────────────────────────────${RESET}"; }

# ── 加载 .env ─────────────────────────────────────────────────────────────────
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-photo}"
THUMBNAIL_PATH="${THUMBNAIL_PATH:-$ROOT/data/thumbs}"

# ── 参数解析 ─────────────────────────────────────────────────────────────────
DO_DB=true
DO_THUMBS=false
AUTO_YES=false

for arg in "$@"; do
  case "$arg" in
    --db-only)    : ;;
    --thumbs)     DO_THUMBS=true ;;
    --yes|-y)     AUTO_YES=true ;;
    --help|-h)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) log_error "未知参数: $arg"; exit 1 ;;
  esac
done

# ── 确认提示 ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${RED}${BOLD}⚠  开发调试数据清理 — 不可恢复！${RESET}"
log_sep
echo ""
$DO_DB    && echo -e "  ${RED}●${RESET} PostgreSQL: 重置所有表 (alembic downgrade base → upgrade head)"
$DO_THUMBS && echo -e "  ${RED}●${RESET} 缩略图:     删除 $THUMBNAIL_PATH"
echo ""
log_sep

if ! $AUTO_YES; then
  printf "确认清空？输入 ${BOLD}yes${RESET} 继续: "
  read -r answer
  if [ "$answer" != "yes" ]; then
    log_warn "已取消"
    exit 0
  fi
fi

echo ""

# ── 检查 Docker 容器是否运行 ──────────────────────────────────────────────────
check_container() {
  local svc="$1"
  if ! docker compose -f "$ROOT/docker-compose.yml" ps "$svc" \
       | grep -qE "running|healthy" 2>/dev/null; then
    log_error "$svc 容器未运行，请先执行: ./scripts/svc.sh start $svc"
    exit 1
  fi
}

# ── 重置数据库 ────────────────────────────────────────────────────────────────
reset_db() {
  check_container postgres

  log_info "重置数据库 (alembic downgrade base)..."
  cd "$ROOT/apps/api"
  [ -d ".venv" ] && source .venv/bin/activate
  alembic downgrade base

  log_info "重新建表 (alembic upgrade head)..."
  alembic upgrade head

  log_ok "数据库已重置为干净状态"
}

# ── 清除缩略图 ────────────────────────────────────────────────────────────────
clear_thumbs() {
  if [ -d "$THUMBNAIL_PATH" ]; then
    log_info "删除缩略图目录: $THUMBNAIL_PATH"
    rm -rf "${THUMBNAIL_PATH:?}/"*
    log_ok "缩略图已清空"
  else
    log_warn "缩略图目录不存在，跳过: $THUMBNAIL_PATH"
  fi
}

# ── 执行 ─────────────────────────────────────────────────────────────────────
$DO_DB     && reset_db
$DO_THUMBS && clear_thumbs

echo ""
log_sep
log_ok "清理完成！现在可以重新扫描：./scripts/svc.sh restart api"
log_sep
echo ""
