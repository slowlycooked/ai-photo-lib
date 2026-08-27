#!/usr/bin/env bash
set -euo pipefail

name="${1:-}"
shift || true

if [ -z "$name" ] || [ "$#" -eq 0 ]; then
  echo "Usage: $0 <ai-photo-name> <command...>" >&2
  exit 1
fi

child_pid=""
stopping=0
watchdog_backoff_initial="${SVC_WATCHDOG_BACKOFF_INITIAL:-1}"
watchdog_backoff_max="${SVC_WATCHDOG_BACKOFF_MAX:-30}"
watchdog_stable_seconds="${SVC_WATCHDOG_STABLE_SECONDS:-60}"

positive_integer_or_default() {
  local value="$1"
  local fallback="$2"

  case "$value" in
    ''|*[!0-9]*|0) printf '%s\n' "$fallback" ;;
    *) printf '%s\n' "$value" ;;
  esac
}

watchdog_backoff_initial="$(positive_integer_or_default "$watchdog_backoff_initial" 1)"
watchdog_backoff_max="$(positive_integer_or_default "$watchdog_backoff_max" 30)"
watchdog_stable_seconds="$(positive_integer_or_default "$watchdog_stable_seconds" 60)"

if [ "$watchdog_backoff_max" -lt "$watchdog_backoff_initial" ]; then
  watchdog_backoff_max="$watchdog_backoff_initial"
fi

log_event() {
  local level="$1"
  local event="$2"
  shift 2

  printf 'timestamp=%s level=%s component=watchdog event=%s service=%s' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$level" "$event" "$name"
  if [ "$#" -gt 0 ]; then
    printf ' %s' "$@"
  fi
  printf '\n'
}

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
  local signal="$1"

  if [ "$stopping" -eq 0 ]; then
    stopping=1
    log_event INFO watchdog_stop "signal=$signal"
  fi

  if [ -n "$child_pid" ] && kill -0 "$child_pid" 2>/dev/null; then
    terminate_tree "$child_pid" TERM
  fi
}

trap 'forward_stop TERM' TERM
trap 'forward_stop INT' INT
trap 'forward_stop HUP' HUP

backoff_seconds="$watchdog_backoff_initial"
attempt=0

while [ "$stopping" -eq 0 ]; do
  attempt=$((attempt + 1))
  started_at="$(date +%s)"
  log_event INFO child_start "attempt=$attempt"

  "$@" &
  child_pid="$!"
  if wait "$child_pid"; then
    exit_code=0
  else
    exit_code="$?"
  fi
  child_pid=""

  if [ "$stopping" -eq 1 ]; then
    exit 0
  fi

  runtime_seconds=$(( $(date +%s) - started_at ))
  log_event WARN child_exit "exit_code=$exit_code" "runtime_seconds=$runtime_seconds"

  if [ "$runtime_seconds" -ge "$watchdog_stable_seconds" ]; then
    backoff_seconds="$watchdog_backoff_initial"
  fi

  log_event WARN restart_scheduled "delay_seconds=$backoff_seconds"
  sleep "$backoff_seconds" || true

  if [ "$backoff_seconds" -lt "$watchdog_backoff_max" ]; then
    backoff_seconds=$((backoff_seconds * 2))
    if [ "$backoff_seconds" -gt "$watchdog_backoff_max" ]; then
      backoff_seconds="$watchdog_backoff_max"
    fi
  fi
done

exit 0
