#!/usr/bin/env bash
set -euo pipefail

name="${1:-}"
shift || true

if [ -z "$name" ] || [ "$#" -eq 0 ]; then
  echo "Usage: $0 <ai-photo-name> <command...>" >&2
  exit 1
fi

child_pid=""

forward_stop() {
  if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
    local pgid=""
    pgid="$(ps -o pgid= -p "$child_pid" 2>/dev/null | tr -d ' ' || true)"
    if [ -n "$pgid" ]; then
      kill -TERM -"$pgid" 2>/dev/null || true
    fi
    kill -TERM "$child_pid" 2>/dev/null || true
  fi
}

trap forward_stop TERM INT HUP

"$@" &
child_pid="$!"
wait "$child_pid"
