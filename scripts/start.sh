#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
PY=$REPO/.venv/bin/python
if [[ ! -x "$PY" ]]; then
  PY=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
fi

# Load Telegram secrets and state config from well-known paths when not already
# set. Only fill in defaults if the files actually exist, so missing-config
# scenarios still fall through to the standard skip path.
_default_secret_env="$HOME/.config/paulshaclaw/paulshaclaw.telegram.secret.env"
_default_state_config="$HOME/.config/paulshaclaw/paulshaclaw.state.json"
if [[ -z "${PSC_TELEGRAM_BOT_TOKEN:-}" && -r "$_default_secret_env" ]]; then
  set -o allexport
  # shellcheck source=/dev/null
  source "$_default_secret_env"
  set +o allexport
fi
if [[ -z "${PSC_STAGE1_CONFIG:-}" && -r "$_default_state_config" ]]; then
  export PSC_STAGE1_CONFIG="$_default_state_config"
fi
unset _default_secret_env _default_state_config

mkdir -p ~/.agents/log
TELEGRAM_LOG=$HOME/.agents/log/telegram.log
TELEGRAM_READY_FILE=$HOME/.agents/run/telegram.ready
TELEGRAM_STARTUP_TIMEOUT=${PSC_TELEGRAM_STARTUP_TIMEOUT:-40}

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
  local footer_env
  local refresh_seconds
  footer_env=""
  if [[ -n "${PAULSHACLAW_CONFIG:-}" ]]; then
    printf -v footer_env 'PAULSHACLAW_CONFIG=%q ' "${PAULSHACLAW_CONFIG}"
  fi
  footer_cmd="#(PYTHONPATH=${REPO} ${footer_env}${PY} -m paulshaclaw.cost.status)"
  existing_right="$(tmux show-option -qv status-right 2>/dev/null || true)"
  refresh_seconds="$(load_stage8_tmux_refresh_seconds | tr -d '\r' | tail -n 1)"
  if [[ ! "${refresh_seconds}" =~ ^[0-9]+$ ]]; then
    refresh_seconds=30
  fi

  tmux set-option status-interval "${refresh_seconds}"
  case "${existing_right}" in
    "${footer_cmd}"*)
      # 完全匹配當前 footer_cmd，無需更新
      return 0
      ;;
    *"paulshaclaw.cost.status"*)
      # 舊版本（路徑不同）：用 bash regex 切片替換，
      # 避免 sed 對 footer_cmd 內含的 / & 等特殊字元踩雷。
      local pattern updated_right
      pattern='^(.*)#\([^)]*paulshaclaw\.cost\.status[^)]*\)(.*)$'
      if [[ "${existing_right}" =~ $pattern ]]; then
        updated_right="${BASH_REMATCH[1]}${footer_cmd}${BASH_REMATCH[2]}"
      else
        updated_right="${footer_cmd}"
      fi
      tmux set-option status-right "${updated_right}"
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
  echo "telegram pid=$TELEGRAM_PID"
fi

if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
  wait "$MONITOR_PID" 2>/dev/null || true
  echo "monitor exited before cockpit start (continuing)" >&2
fi

# Stage 11: cockpit TUI (background with real stdin so Textual gets a TTY)
# Background processes default to /dev/null stdin; Textual raises
# ParseError("end of file reached") immediately. Probe /dev/tty in a subshell
# (avoids "No such device or address" when there is no controlling terminal,
# e.g. in CI or the test harness). Use /dev/null as fallback.
_cockpit_stdin=/dev/null
if (exec </dev/tty) 2>/dev/null; then
  _cockpit_stdin=/dev/tty
fi
"$PY" -m paulshaclaw.cockpit --cockpit-pane "${TMUX_PANE:?must run inside tmux}" < "$_cockpit_stdin" &
COCKPIT_PID=$!
if wait "$COCKPIT_PID"; then
  exit 0
else
  cockpit_status=$?
  exit "$cockpit_status"
fi
