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

load_stage8_tmux_refresh_seconds() {
  "$PY" -c '
from pathlib import Path
import os
from paulshaclaw.cost.config import load_cost_config

config_path = os.environ.get("PAULSHACLAW_CONFIG")
config = load_cost_config(config_path=Path(config_path) if config_path else None)
print(config.tmux_refresh_seconds)
' 2>/dev/null || printf '30\n'
}

start_cost_refresh_loop() {
  if [[ -z "${TMUX:-}" ]]; then
    return 0
  fi
  if [[ "${PSC_COST_REFRESH_DISABLED:-0}" == "1" ]]; then
    echo "cost refresh loop disabled (PSC_COST_REFRESH_DISABLED=1)"
    return 0
  fi
  local interval
  interval="$(load_stage8_tmux_refresh_seconds | tr -d '\r' | tail -n 1)"
  if [[ ! "${interval}" =~ ^[0-9]+$ ]]; then
    interval=30
  fi
  mkdir -p "$HOME/.agents/log"
  local cost_log="$HOME/.agents/log/cost.log"
  (
    while true; do
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.cost --once || true
      sleep "$interval"
    done
  ) 200>&- >>"$cost_log" 2>&1 &
  COST_REFRESH_PID=$!
  echo "cost refresh pid=$COST_REFRESH_PID (interval=${interval}s)"
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  start_cost_refresh_loop
  if [[ -n "${COST_REFRESH_PID:-}" ]]; then
    wait "$COST_REFRESH_PID"
  fi
fi
