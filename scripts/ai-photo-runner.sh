#!/usr/bin/env bash
set -euo pipefail

name="${1:-}"
shift || true

if [ -z "$name" ] || [ "$#" -eq 0 ]; then
  echo "Usage: $0 <ai-photo-name> <command...>" >&2
  exit 1
fi

child_pid=""

terminate_tree() {
  local pid="$1"
  local sig="${2:-TERM}"
  local child

  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    terminate_tree "$child" "$sig"
  done

  kill "-$sig" "$pid" 2>/dev/null || true
}

forward_stop() {
  if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
    terminate_tree "$child_pid" TERM
  fi
}

trap forward_stop TERM INT HUP

"$@" &
child_pid="$!"
wait "$child_pid"
