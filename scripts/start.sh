#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
PY=$REPO/.venv/bin/python

mkdir -p ~/.agents/log
TELEGRAM_LOG=$HOME/.agents/log/telegram.log
TELEGRAM_READY_FILE=$HOME/.agents/run/telegram.ready
TELEGRAM_STARTUP_TIMEOUT=${PSC_TELEGRAM_STARTUP_TIMEOUT:-40}

cleanup() {
  if [[ "${CLEANED_UP:-0}" -eq 1 ]]; then
    return
  fi
  CLEANED_UP=1
  trap - EXIT INT TERM

  for pid in "${TELEGRAM_PID:-}" "${MONITOR_PID:-}" "${COCKPIT_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  for pid in "${TELEGRAM_PID:-}" "${MONITOR_PID:-}" "${COCKPIT_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
}

cleanup_term() {
  cleanup
  exit 143
}

cleanup_int() {
  cleanup
  exit 130
}

trap cleanup EXIT
trap cleanup_int INT
trap cleanup_term TERM

# Telegram listener (background when config is present)
telegram_token_present=0
telegram_config_present=0
telegram_config_readable=0
if [[ -n "${PSC_TELEGRAM_BOT_TOKEN:-}" ]]; then
  telegram_token_present=1
fi
if [[ -n "${PSC_STAGE1_CONFIG:-}" ]]; then
  telegram_config_present=1
  if [[ -r "${PSC_STAGE1_CONFIG}" ]]; then
    telegram_config_readable=1
  fi
fi

if [[ "$telegram_token_present" -eq 0 && "$telegram_config_present" -eq 0 ]]; then
  echo "telegram skipped: missing PSC_TELEGRAM_BOT_TOKEN or PSC_STAGE1_CONFIG"
elif [[ "$telegram_token_present" -eq 1 && "$telegram_config_present" -eq 1 && "$telegram_config_readable" -eq 1 ]]; then
  :
else
  echo "telegram startup requires both PSC_TELEGRAM_BOT_TOKEN and readable PSC_STAGE1_CONFIG" >&2
  exit 1
fi

# Stage 9: project-monitor (background)
"$PY" -m paulshaclaw.monitor >> ~/.agents/log/monitor.log 2>&1 &
MONITOR_PID=$!
echo "monitor pid=$MONITOR_PID"

if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
  wait "$MONITOR_PID" 2>/dev/null || true
  echo "monitor exited before startup" >&2
  exit 1
fi

if [[ "$telegram_token_present" -eq 1 && "$telegram_config_present" -eq 1 && "$telegram_config_readable" -eq 1 ]]; then
  mkdir -p "$(dirname "$TELEGRAM_READY_FILE")"
  : > "$TELEGRAM_READY_FILE"
  export PSC_TELEGRAM_READY_FILE="$TELEGRAM_READY_FILE"
  "$PY" -m paulshaclaw.bot.listener >> "$TELEGRAM_LOG" 2>&1 &
  TELEGRAM_PID=$!
  telegram_ready_deadline=$((SECONDS + TELEGRAM_STARTUP_TIMEOUT))
  while true; do
    if [[ -s "$TELEGRAM_READY_FILE" ]]; then
      break
    fi
    if ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
      wait "$TELEGRAM_PID" 2>/dev/null || true
      echo "telegram listener exited before ready" >&2
      exit 1
    fi
    if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
      wait "$MONITOR_PID" 2>/dev/null || true
      echo "monitor exited before telegram ready" >&2
      exit 1
    fi
    if (( SECONDS >= telegram_ready_deadline )); then
      echo "telegram listener readiness timeout" >&2
      exit 1
    fi
    sleep 0.05
  done
  if ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
    wait "$TELEGRAM_PID" 2>/dev/null || true
    echo "telegram listener exited after ready" >&2
    exit 1
  fi
  telegram_ready_stabilize_deadline=$((SECONDS + 1))
  while true; do
    telegram_state=$(ps -o stat= -p "$TELEGRAM_PID" 2>/dev/null | tr -d '[:space:]')
    if [[ -z "$telegram_state" || "$telegram_state" == *Z* ]]; then
      wait "$TELEGRAM_PID" 2>/dev/null || true
      echo "telegram listener not healthy after ready" >&2
      exit 1
    fi
    if (( SECONDS >= telegram_ready_stabilize_deadline )); then
      break
    fi
    sleep 0.05
  done
  if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    wait "$MONITOR_PID" 2>/dev/null || true
    echo "monitor exited before cockpit start" >&2
    exit 1
  fi
  echo "telegram pid=$TELEGRAM_PID"
fi

if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
  wait "$MONITOR_PID" 2>/dev/null || true
  echo "monitor exited before cockpit start" >&2
  exit 1
fi

# Stage 11: cockpit TUI (foreground status path, requires tmux)
"$PY" -m paulshaclaw.cockpit --cockpit-pane "${TMUX_PANE:?must run inside tmux}" &
COCKPIT_PID=$!
if wait "$COCKPIT_PID"; then
  exit 0
else
  cockpit_status=$?
  exit "$cockpit_status"
fi
