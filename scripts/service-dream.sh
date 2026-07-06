#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
PY="$REPO/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
fi

if [[ "${PSC_DREAM_DISABLED:-0}" == "1" ]]; then
  echo "dream loop disabled (PSC_DREAM_DISABLED=1)"
  exit 0
fi

dream_root="${PSC_DREAM_ROOT_OVERRIDE:-${PSC_MEMORY_ROOT:-$HOME/.agents/memory}}"
if [[ ! -e "$dream_root" ]]; then
  echo "dream loop skipped: memory root not found ($dream_root)" >&2
  exit 0
fi

interval="${PSC_DREAM_INTERVAL_OVERRIDE:-${PSC_DREAM_INTERVAL_SECONDS:-3600}}"
if [[ ! "$interval" =~ ^[0-9]+$ ]]; then
  interval=3600
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
  sleep "$interval" &
  child_pid=$!
  wait "$child_pid"
  child_pid=""
  PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run \
    --memory-root "$dream_root" --require-idle --promoter llm \
    --instruction-root "$HOME/.claude/CLAUDE.md" \
    --instruction-root "$HOME/CLAUDE.md" \
    --instruction-root "$HOME/AGENTS.md" \
    --instruction-root "$HOME/GEMINI.md" \
    --instruction-root "$HOME/.codex" \
    --instruction-root "$HOME/.agents" \
    --instruction-root "$HOME/.gemini" \
    --instruction-root "$HOME/prj_pri" \
    --instruction-root "$HOME/prj_arc" &
  child_pid=$!
  wait "$child_pid" 2>/dev/null || true
  child_pid=""
done
