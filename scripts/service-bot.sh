#!/usr/bin/env bash
set -euo pipefail

_psc_service_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${REPO:-}" ]]; then
  REPO="$(cd "$_psc_service_dir/.." && pwd)"
fi
if [[ -z "${PY:-}" ]]; then
  PY="$REPO/.venv/bin/python"
  if [[ ! -x "$PY" ]]; then
    PY=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
  fi
fi
unset _psc_service_dir

: "${TELEGRAM_LOG:=$HOME/.agents/log/telegram.log}"
: "${TELEGRAM_READY_FILE:=$HOME/.agents/run/telegram.ready}"
: "${TELEGRAM_STARTUP_TIMEOUT:=${PSC_TELEGRAM_STARTUP_TIMEOUT:-40}}"

run_telegram_listener_once() {
  local telegram_listener_pid=""
  trap 'if [[ -n "${telegram_listener_pid:-}" ]]; then kill -TERM "$telegram_listener_pid" 2>/dev/null || true; wait "$telegram_listener_pid" 2>/dev/null || true; fi; exit 143' INT TERM

  mkdir -p "$HOME/.agents/log" "$(dirname "$TELEGRAM_READY_FILE")"
  : > "$TELEGRAM_READY_FILE"
  export PSC_TELEGRAM_READY_FILE="$TELEGRAM_READY_FILE"
  PYTHONPATH="$REPO" "$PY" -m paulshaclaw.bot.listener 200>&- >> "$TELEGRAM_LOG" 2>&1 &
  telegram_listener_pid=$!

  local telegram_ready_deadline=$((SECONDS + TELEGRAM_STARTUP_TIMEOUT))
  while true; do
    if [[ -s "$TELEGRAM_READY_FILE" ]]; then
      break
    fi
    if ! kill -0 "$telegram_listener_pid" 2>/dev/null; then
      wait "$telegram_listener_pid" 2>/dev/null || true
      echo "telegram listener exited before ready" >&2
      return 1
    fi
    if (( SECONDS >= telegram_ready_deadline )); then
      kill -TERM "$telegram_listener_pid" 2>/dev/null || true
      wait "$telegram_listener_pid" 2>/dev/null || true
      echo "telegram listener readiness timeout" >&2
      return 1
    fi
    sleep 0.05
  done

  if ! kill -0 "$telegram_listener_pid" 2>/dev/null; then
    wait "$telegram_listener_pid" 2>/dev/null || true
    echo "telegram listener exited after ready" >&2
    return 1
  fi

  local telegram_ready_stabilize_deadline=$((SECONDS + 1))
  local telegram_state
  while true; do
    telegram_state=$(ps -o stat= -p "$telegram_listener_pid" 2>/dev/null | tr -d '[:space:]')
    if [[ -z "$telegram_state" || "$telegram_state" == *Z* ]]; then
      wait "$telegram_listener_pid" 2>/dev/null || true
      echo "telegram listener not healthy after ready" >&2
      return 1
    fi
    if (( SECONDS >= telegram_ready_stabilize_deadline )); then
      break
    fi
    sleep 0.05
  done

  echo "telegram pid=$telegram_listener_pid"
  if wait "$telegram_listener_pid"; then
    return 0
  fi
  local status=$?
  echo "telegram listener exited unexpectedly (status=$status)" >&2
  return "$status"
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  run_telegram_listener_once
fi
