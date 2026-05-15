#!/usr/bin/env bash
# scripts/dev-up.sh — Start infrastructure services for local development
# The API and Web are run separately (uvicorn + vite dev server).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

# ── Load root .env so we can read port variables ──────────────────────────────
ENV_FILE="$ROOT/.env"
if [ -f "$ENV_FILE" ]; then
  # Export only simple KEY=VALUE lines; skip comments and blank lines
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^[A-Z_]+=.+' "$ENV_FILE")
  set +a
fi

# Defaults if not set
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5432}"
REDIS_HOST_PORT="${REDIS_HOST_PORT:-6379}"

echo "▶ Starting postgres (host port $POSTGRES_HOST_PORT) and redis (host port $REDIS_HOST_PORT)..."
cd "$ROOT"
docker compose up -d postgres redis

echo "▶ Waiting for postgres to be healthy..."
until docker compose exec postgres pg_isready -U photo -d photo > /dev/null 2>&1; do
  sleep 1
done

echo "▶ Running migrations..."
cd apps/api
# Activate venv if present
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi
alembic upgrade head

echo ""
echo "✓ Infrastructure ready!"
echo ""
echo "  PostgreSQL : localhost:${POSTGRES_HOST_PORT} (db=photo, user=photo)"
echo "  Redis      : localhost:${REDIS_HOST_PORT}"
echo ""
echo "Now start the API:"
echo "  cd apps/api && uvicorn app.main:app --reload"
echo ""
echo "And the web dev server:"
echo "  cd apps/web && npm run dev"
