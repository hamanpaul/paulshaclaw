#!/usr/bin/env bash
set -euo pipefail

REPO=/home/paul_chen/prj_pri/paulshaclaw
PY=$REPO/.venv/bin/python

mkdir -p ~/.agents/log
TELEGRAM_LOG=$HOME/.agents/log/telegram.log

load_stage8_tmux_refresh_seconds() {
  "${PY}" -c '
from pathlib import Path
import os
from paulshaclaw.cost.config import load_cost_config

config_path = os.environ.get("PAULSHACLAW_CONFIG")
config = load_cost_config(config_path=Path(config_path) if config_path else None)
print(config.tmux_refresh_seconds)
' 2>/dev/null || printf '30\n'
}

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

apply_stage8_footer() {
  if [[ -z "${TMUX:-}" ]]; then
    return 0
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    return 0
  fi

  local footer_cmd
  local existing_right
  local refresh_seconds
  footer_cmd="#(${PY} -m paulshaclaw.cost.status)"
  existing_right="$(tmux show-option -qv status-right 2>/dev/null || true)"
  refresh_seconds="$(load_stage8_tmux_refresh_seconds | tr -d '\r' | tail -n 1)"
  if [[ ! "${refresh_seconds}" =~ ^[0-9]+$ ]]; then
    refresh_seconds=30
  fi

  tmux set-option status-interval "${refresh_seconds}"
  case "${existing_right}" in
    *"paulshaclaw.cost.status"*)
      return 0
      ;;
    "")
      tmux set-option status-right "${footer_cmd}"
      ;;
    *)
      tmux set-option status-right "${existing_right} ${footer_cmd}"
      ;;
  esac
}

apply_stage8_footer

# Stage 9: project-monitor (background)
"$PY" -m paulshaclaw.monitor >> ~/.agents/log/monitor.log 2>&1 &
MONITOR_PID=$!
echo "monitor pid=$MONITOR_PID"

# Telegram listener (background when config is present)
if [[ -n "${PSC_TELEGRAM_BOT_TOKEN:-}" && -n "${PSC_STAGE1_CONFIG:-}" && -r "${PSC_STAGE1_CONFIG}" ]]; then
  "$PY" -m paulshaclaw.bot.listener >> "$TELEGRAM_LOG" 2>&1 &
  TELEGRAM_PID=$!
  telegram_ready_deadline=$((SECONDS + 10))
  while true; do
    if grep -q "Telegram listener ready" "$TELEGRAM_LOG" 2>/dev/null; then
      break
    fi
    if ! kill -0 "$TELEGRAM_PID" 2>/dev/null; then
      wait "$TELEGRAM_PID" 2>/dev/null || true
      echo "telegram listener exited before ready" >&2
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
