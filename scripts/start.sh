#!/usr/bin/env bash
set -euo pipefail

REPO=/home/paul_chen/prj_pri/paulshaclaw
PY=$REPO/.venv/bin/python

mkdir -p ~/.agents/log

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

# Stage 9: project-monitor (background)
"$PY" -m paulshaclaw.monitor >> ~/.agents/log/monitor.log 2>&1 &
MONITOR_PID=$!
echo "monitor pid=$MONITOR_PID"

# Telegram listener (background when config is present)
if [[ -n "${PSC_TELEGRAM_BOT_TOKEN:-}" && -n "${PSC_STAGE1_CONFIG:-}" && -r "${PSC_STAGE1_CONFIG}" ]]; then
  "$PY" -m paulshaclaw.bot.listener >> ~/.agents/log/telegram.log 2>&1 &
  TELEGRAM_PID=$!
  sleep 0.1
  if ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
    wait "$TELEGRAM_PID" 2>/dev/null || true
    echo "telegram listener exited immediately" >&2
    exit 1
  fi
  echo "telegram pid=$TELEGRAM_PID"
else
  echo "telegram skipped: missing PSC_TELEGRAM_BOT_TOKEN or PSC_STAGE1_CONFIG"
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
