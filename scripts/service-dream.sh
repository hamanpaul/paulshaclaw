#!/usr/bin/env bash
set -euo pipefail

_psc_service_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${REPO:-}" ]]; then
  REPO="$(cd "$_psc_service_dir/.." && pwd)"
fi
if [[ -z "${PY:-}" ]]; then
  # Prefer PSC_PYTHON / system python3 (planes in ~/.local) over the repo .venv.
  PY="$(command -v "${PSC_PYTHON:-python3}" 2>/dev/null || true)"
  [[ -n "$PY" ]] || PY="$REPO/.venv/bin/python"
fi
unset _psc_service_dir

start_dream_loop() {
  if [[ "${PSC_DREAM_DISABLED:-0}" == "1" ]]; then
    echo "dream loop disabled (PSC_DREAM_DISABLED=1)"
    return 0
  fi
  # #125 cutover：dream 蒸餾由 paulsha-hippo 提供。偵測順序（#228 F2）：
  # HIPPO_BIN > PATH 上的 hippo（pipx 情境）> repo venv 模組；全無 → 跳過+警告。
  local hippo_bin="${HIPPO_BIN:-}"
  if [[ "$hippo_bin" == "disabled" ]]; then
    hippo_bin=""
  elif [[ -z "$hippo_bin" ]]; then
    hippo_bin="$(command -v hippo || true)"
  fi
  if [[ -z "$hippo_bin" ]] && ! "$PY" -c "import paulsha_hippo" >/dev/null 2>&1; then
    echo "dream loop skipped: paulsha-hippo 未安裝（pipx install git+https://github.com/hamanpaul/paulsha-hippo）" >&2
    return 0
  fi
  local dream_root="${PSC_MEMORY_ROOT:-$HOME/.agents/memory}"
  if [[ ! -e "$dream_root" ]]; then
    echo "dream loop skipped: memory root not found ($dream_root)" >&2
    return 0
  fi
  local interval="${PSC_DREAM_INTERVAL_SECONDS:-3600}"
  if [[ ! "$interval" =~ ^[0-9]+$ ]]; then
    interval=3600
  fi
  mkdir -p "$HOME/.agents/log"
  local dream_log="$HOME/.agents/log/dream.log"
  # hippo binary 可用時交給 hippo 自有 supervise（首輪延後語意相同）
  if [[ -n "$hippo_bin" ]]; then
    "$hippo_bin" dream supervise --interval "$interval" --memory-root "$dream_root" \
      >>"$dream_log" 2>&1 &
    DREAM_PID=$!
    echo "dream pid=$DREAM_PID (hippo supervise, interval=${interval}s, root=$dream_root)"
    return 0
  fi
  (
    while true; do
      # Defer the first run by one full interval: right after boot the 1-minute
      # load average is still near zero, so the idle gate would always pass and
      # stack a full dream pass on top of the startup burst.
      sleep "$interval"
      # #176: doc-fragment 產生端過濾。roots = instruction_corpus.default_roots()，
      # 與 moc/runner 的 index 端 broad corpus 同源——index 排除什麼、產生端就擋什麼。
      "$PY" -m paulsha_hippo.cli dream run \
        --memory-root "$dream_root" --require-idle --promoter llm \
        --instruction-root "$HOME/.claude/CLAUDE.md" \
        --instruction-root "$HOME/CLAUDE.md" \
        --instruction-root "$HOME/AGENTS.md" \
        --instruction-root "$HOME/GEMINI.md" \
        --instruction-root "$HOME/.codex" \
        --instruction-root "$HOME/.agents" \
        --instruction-root "$HOME/.gemini" \
        --instruction-root "$HOME/prj_pri" \
        ${PSC_EXTRA_CORPUS_ROOT:+--instruction-root "$PSC_EXTRA_CORPUS_ROOT"} \
        >>"$dream_log" 2>&1 || true
    done
  ) 200>&- &
  DREAM_PID=$!
  echo "dream pid=$DREAM_PID (interval=${interval}s, root=$dream_root)"
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  start_dream_loop
  if [[ -n "${DREAM_PID:-}" ]]; then
    wait "$DREAM_PID"
  fi
fi
