#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
fi

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

if [[ "${PSC_COST_REQUIRE_TMUX:-0}" == "1" && -z "${TMUX:-}" ]]; then
  exit 0
fi
if [[ "${PSC_COST_REFRESH_DISABLED:-0}" == "1" ]]; then
  echo "cost refresh loop disabled (PSC_COST_REFRESH_DISABLED=1)"
  exit 0
fi

interval="${PSC_COST_REFRESH_INTERVAL_OVERRIDE:-}"
if [[ ! "${interval}" =~ ^[0-9]+$ ]]; then
  interval="$(load_stage8_tmux_refresh_seconds | tr -d '\r' | tail -n 1)"
fi
if [[ ! "${interval}" =~ ^[0-9]+$ ]]; then
  interval=30
fi

child_pid=""
terminate() {
  if [[ -n "$child_pid" ]]; then
    kill -TERM "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  exit 143
}
trap terminate TERM INT

while true; do
  PYTHONPATH="$REPO" "$PY" -m paulshaclaw.cost --once &
  child_pid=$!
  wait "$child_pid" 2>/dev/null || true
  child_pid=""
  sleep "$interval" &
  child_pid=$!
  wait "$child_pid"
  child_pid=""
done
