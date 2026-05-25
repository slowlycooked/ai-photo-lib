#!/usr/bin/env bash
# scripts/init-db.sh — Run Alembic migrations against a running Postgres instance
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$SCRIPT_DIR/../apps/api"

echo "▶ Running database migrations..."
cd "$API_DIR"
if [ -x ".venv/bin/python" ]; then
  .venv/bin/python -m alembic upgrade head
else
  python3 -m alembic upgrade head
fi
echo "✓ Migrations complete."
