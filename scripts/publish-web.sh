#!/usr/bin/env bash
# scripts/publish-web.sh — build and publish desktop/mobile web artifacts
#
# Usage:
#   ./scripts/publish-web.sh \
#     --desktop-dir /usr/share/nginx/html \
#     --mobile-dir /usr/share/nginx/html/m
#
# Optional:
#   --dry-run    Show actions without copying files
#   --no-build   Skip npm build steps and only sync existing dist artifacts

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$ROOT/apps/web"
MOBILE_WEB_DIR="$ROOT/apps/mobile-web"
WEB_DIST="$WEB_DIR/dist"
MOBILE_DIST="$MOBILE_WEB_DIR/dist"

DESKTOP_DIR=""
MOBILE_DIR=""
DRY_RUN=0
NO_BUILD=0

say() {
  echo "[publish-web] $*"
}

die() {
  echo "[publish-web][error] $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/publish-web.sh --desktop-dir <path> --mobile-dir <path> [--dry-run] [--no-build]

Required:
  --desktop-dir  Target directory for desktop web artifact (apps/web/dist)
  --mobile-dir   Target directory for mobile web artifact (apps/mobile-web/dist)

Optional:
  --dry-run      Print planned operations only, no file writes
  --no-build     Do not run npm build; only sync existing dist directories
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --desktop-dir)
      DESKTOP_DIR="${2:-}"
      shift 2
      ;;
    --mobile-dir)
      MOBILE_DIR="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-build)
      NO_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[ -n "$DESKTOP_DIR" ] || die "Missing --desktop-dir"
[ -n "$MOBILE_DIR" ] || die "Missing --mobile-dir"

if [ "$DESKTOP_DIR" = "$MOBILE_DIR" ]; then
  die "--desktop-dir and --mobile-dir must be different directories"
fi

if ! command -v npm >/dev/null 2>&1; then
  die "npm not found in PATH"
fi

sync_dist() {
  local src="$1"
  local dst="$2"

  if [ ! -d "$src" ]; then
    die "Source dist not found: $src"
  fi

  if command -v rsync >/dev/null 2>&1; then
    if [ "$DRY_RUN" -eq 1 ]; then
      say "[dry-run] rsync -a --delete '$src/' '$dst/'"
    else
      mkdir -p "$dst"
      rsync -a --delete "$src/" "$dst/"
    fi
    return 0
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    say "[dry-run] rm -rf '$dst'/* && copy '$src'/* -> '$dst/'"
    return 0
  fi

  mkdir -p "$dst"
  find "$dst" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  cp -R "$src"/. "$dst"/
}

if [ "$NO_BUILD" -eq 0 ]; then
  say "Building desktop web artifact..."
  (
    cd "$WEB_DIR"
    npm run build
  )

  say "Building mobile web artifact..."
  (
    cd "$MOBILE_WEB_DIR"
    npm run build
  )
else
  say "Skipping build step (--no-build)"
fi

say "Publishing desktop artifact: $WEB_DIST -> $DESKTOP_DIR"
sync_dist "$WEB_DIST" "$DESKTOP_DIR"

say "Publishing mobile artifact: $MOBILE_DIST -> $MOBILE_DIR"
sync_dist "$MOBILE_DIST" "$MOBILE_DIR"

if [ "$DRY_RUN" -eq 1 ]; then
  say "Dry-run completed."
else
  say "Publish completed."
fi
