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

# Telegram listener (background)
"$PY" -m paulshaclaw.bot.listener >> ~/.agents/log/telegram.log 2>&1 &
TELEGRAM_PID=$!
echo "telegram pid=$TELEGRAM_PID"

# Stage 11: cockpit TUI (foreground status path, requires tmux)
"$PY" -m paulshaclaw.cockpit --cockpit-pane "${TMUX_PANE:?must run inside tmux}" &
COCKPIT_PID=$!
if wait "$COCKPIT_PID"; then
  exit 0
else
  cockpit_status=$?
  exit "$cockpit_status"
fi
