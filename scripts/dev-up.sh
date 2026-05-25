#!/usr/bin/env bash
# scripts/dev-up.sh — convenience wrapper for MacBook development

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"
DEPLOY_PROFILE="${DEPLOY_PROFILE:-dev}" ./scripts/svc.sh start postgres api web
