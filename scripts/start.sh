#!/usr/bin/env bash
set -euo pipefail

start_bot_supervised() {
  local delay="${PSC_BOT_BACKOFF_BASE:-5}"
  if [[ ! "$delay" =~ ^[0-9]+$ ]]; then
    delay=5
  fi
  if (( delay > 120 )); then delay=120; fi  # 初值也套 120s 上限（誤設 PSC_BOT_BACKOFF_BASE 防護，review nitpick）
  local -a cmd=("$@")
  if [[ "${#cmd[@]}" -eq 0 ]]; then
    echo "start_bot_supervised requires a command" >&2
    return 1
  fi
  (
    if [[ -n "${PSC_BOT_SUPERVISOR_LOG:-}" ]]; then
      exec >>"$PSC_BOT_SUPERVISOR_LOG" 2>&1
    fi
    local child_pid="" respawn_count=0 status=0
    trap 'if [[ -n "${child_pid:-}" ]]; then kill -TERM "$child_pid" 2>/dev/null || true; wait "$child_pid" 2>/dev/null || true; fi; exit 0' INT TERM
    while true; do
      "${cmd[@]}" &
      child_pid=$!
      if wait "$child_pid"; then
        child_pid=""
        break
      fi
      status=$?
      child_pid=""
      respawn_count=$((respawn_count + 1))
      echo "bot exited unexpectedly (status=$status); respawn #$respawn_count in ${delay}s" >&2
      sleep "$delay"
      if (( delay > 0 )); then
        delay=$((delay * 6))
        if (( delay > 120 )); then
          delay=120
        fi
      fi
    done
  ) &
  TELEGRAM_PID=$!
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

start_lock="${XDG_RUNTIME_DIR:-/tmp}/paulshaclaw-start.lock"
exec 200>"$start_lock"
flock -n 200 || { echo 已有實例在跑; exit 1; }

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

  for pid in "${TELEGRAM_PID:-}" "${MONITOR_PID:-}" "${DREAM_PID:-}" "${MANAGER_PID:-}" "${COCKPIT_PID:-}" "${COST_REFRESH_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  for pid in "${TELEGRAM_PID:-}" "${MONITOR_PID:-}" "${DREAM_PID:-}" "${COCKPIT_PID:-}" "${COST_REFRESH_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  if [[ -n "${MANAGER_PID:-}" ]]; then
    if [[ "${MANAGER_PID_OWNED:-1}" == "1" ]]; then
      # bounded graceful wait (100 x 0.05s = 5s), then SIGKILL fallback so a
      # wedged manager cannot hang shutdown indefinitely.
      local shutdown_checks=100
      while (( shutdown_checks > 0 )) && kill -0 "$MANAGER_PID" 2>/dev/null; do
        sleep 0.05
        shutdown_checks=$((shutdown_checks - 1))
      done
      if kill -0 "$MANAGER_PID" 2>/dev/null; then
        kill -KILL "$MANAGER_PID" 2>/dev/null || true
      fi
      wait "$MANAGER_PID" 2>/dev/null || true
    else
      wait_for_manager_shutdown "$MANAGER_PID"
    fi
  fi
  systemctl --user stop "${PSC_INSTANCE:-paulshaclaw}-manager.timer" 2>/dev/null || true
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
  footer_cmd="#(PYTHONPATH=${REPO} ${footer_env}${PY} -m paulshaclaw.cost.status --no-refresh)"
  existing_right="$(tmux show-option -qv status-right 2>/dev/null || true)"
  refresh_seconds="$(load_stage8_tmux_refresh_seconds | tr -d '\r' | tail -n 1)"
  if [[ ! "${refresh_seconds}" =~ ^[0-9]+$ ]]; then
    refresh_seconds=30
  fi

  tmux set-option status-interval "${refresh_seconds}"
  # tmux defaults status-right-length to 40, which clips the footer mid-segment
  # (e.g. "cc~ 5h:82%"). Widen it so the full cdx/cc/cpt line is visible.
  tmux set-option status-right-length 200
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

# Stage 8: cost-snapshot refresh loop. The tmux footer renders with --no-refresh
# (cheap, only reads the cache), so this throttled background loop owns the
# actual rebuild. Keeping the heavy collect out of the per-interval tmux #()
# render is what stops it from piling up and OOM-ing the WSL VM. Bound to the
# start.sh lifecycle; disable with PSC_COST_REFRESH_DISABLED=1.
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
  local cost_log="$HOME/.agents/log/cost.log"
  # Redirect the whole subshell (including sleep) to the log so no child keeps
  # the parent's stdout pipe open after start.sh exits.
  (
    while true; do
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.cost --once || true
      sleep "$interval"
    done
  ) 200>&- >>"$cost_log" 2>&1 &
  COST_REFRESH_PID=$!
  echo "cost refresh pid=$COST_REFRESH_PID (interval=${interval}s)"
}

apply_stage8_footer
start_cost_refresh_loop

# Stage 2: memory dream loop (atomize + janitor + moc), idle-gated.
# Lifecycle is bound to start.sh — launched here, torn down by cleanup() with
# the other background services. Disable with PSC_DREAM_DISABLED=1; tune cadence
# with PSC_DREAM_INTERVAL_SECONDS (default 3600).
start_dream_loop() {
  if [[ "${PSC_DREAM_DISABLED:-0}" == "1" ]]; then
    echo "dream loop disabled (PSC_DREAM_DISABLED=1)"
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
  local dream_log="$HOME/.agents/log/dream.log"
  (
    while true; do
      # Defer the first run by one full interval: right after boot the 1-minute
      # load average is still near zero, so the idle gate would always pass and
      # stack a full dream pass on top of the startup burst.
      sleep "$interval"
      # #176: doc-fragment 產生端過濾。roots = instruction_corpus.default_roots()，
      # 與 moc/runner 的 index 端 broad corpus 同源——index 排除什麼、產生端就擋什麼。
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
        --instruction-root "$HOME/prj_arc" \
        >>"$dream_log" 2>&1 || true
    done
  ) 200>&- &
  DREAM_PID=$!
  echo "dream pid=$DREAM_PID (interval=${interval}s, root=$dream_root)"
}

stop_legacy_manager_timer() {
  local instance="${PSC_INSTANCE:-paulshaclaw}"
  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    return 0
  fi
  systemctl --user stop "${instance}-manager.timer" "${instance}-manager.service" >/dev/null 2>&1 || true
  systemctl --user disable "${instance}-manager.timer" >/dev/null 2>&1 || true
}

manager_lock_path() {
  local control_root="${PSC_CONTROL_ROOT:-$HOME/.agents/control}"
  printf '%s\n' "$control_root/manager.lock"
}

is_live_manager_pid() {
  local pid="$1"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  if [[ ! -r "/proc/$pid/cmdline" ]]; then
    return 1
  fi
  local cmdline_parts=()
  local idx
  mapfile -d '' -t cmdline_parts <"/proc/$pid/cmdline"
  for ((idx = 0; idx + 1 < ${#cmdline_parts[@]}; idx++)); do
    if [[ "${cmdline_parts[$idx]}" == "-m" && "${cmdline_parts[$((idx + 1))]}" == "paulshaclaw.coordinator.manager_daemon" ]]; then
      return 0
    fi
  done
  return 1
}

read_live_manager_pid() {
  local lock_path
  lock_path="$(manager_lock_path)"
  if [[ ! -f "$lock_path" ]]; then
    return 0
  fi
  local owner_pid
  owner_pid="$(sed -n 's/.*"pid":[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$lock_path" | head -n 1)"
  if [[ -n "$owner_pid" ]] && is_live_manager_pid "$owner_pid"; then
    printf '%s\n' "$owner_pid"
  fi
}

read_manager_lock_owner_pid() {
  local lock_path
  lock_path="$(manager_lock_path)"
  if [[ ! -f "$lock_path" ]]; then
    return 0
  fi
  sed -n 's/.*"pid":[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$lock_path" | head -n 1
}

wait_for_manager_shutdown() {
  local pid="$1"
  local shutdown_checks=100
  local lock_owner_pid
  while (( shutdown_checks > 0 )); do
    lock_owner_pid="$(read_manager_lock_owner_pid)"
    if ! is_live_manager_pid "$pid" && [[ "$lock_owner_pid" != "$pid" ]]; then
      return 0
    fi
    shutdown_checks=$((shutdown_checks - 1))
    if (( shutdown_checks == 0 )); then
      return 0
    fi
    sleep 0.05
  done
}

start_manager_loop() {
  stop_legacy_manager_timer
  if [[ "${PSC_MANAGER_DAEMON_DISABLED:-0}" == "1" ]]; then
    echo "manager loop disabled (PSC_MANAGER_DAEMON_DISABLED=1)"
    return 0
  fi
  local manager_log="$HOME/.agents/log/manager.log"
  (
    PYTHONPATH="$REPO" "$PY" -m paulshaclaw.coordinator.manager_daemon
  ) 200>&- >>"$manager_log" 2>&1 &
  MANAGER_PID=$!
  MANAGER_PID_OWNED=1
  local manager_startup_checks=20
  local manager_state
  while (( manager_startup_checks > 0 )); do
    manager_state="$(ps -o stat= -p "$MANAGER_PID" 2>/dev/null | tr -d '[:space:]' || true)"
    if [[ -z "$manager_state" || "$manager_state" == *Z* ]]; then
      local existing_manager_pid
      existing_manager_pid="$(read_live_manager_pid)"
      wait "$MANAGER_PID" 2>/dev/null || true
      if [[ -n "$existing_manager_pid" && "$existing_manager_pid" != "$MANAGER_PID" ]]; then
        MANAGER_PID="$existing_manager_pid"
        MANAGER_PID_OWNED=0
        echo "manager pid=$MANAGER_PID (adopted existing)"
        return 0
      fi
      echo "manager daemon exited before startup" >&2
      exit 1
    fi
    manager_startup_checks=$((manager_startup_checks - 1))
    if (( manager_startup_checks == 0 )); then
      break
    fi
    sleep 0.05
  done
  echo "manager pid=$MANAGER_PID"
}

# Phase C: persona manager tick via systemd --user timer. start.sh 不擁有 manager
# 進程，只 toggle；systemctl --user 不可用（WSL 無 user systemd）→ graceful skip。
# 停用：PSC_MANAGER_DISABLED=1。
start_manager_service() {
  if [[ "${PSC_MANAGER_DISABLED:-0}" == "1" ]]; then
    echo "manager service disabled (PSC_MANAGER_DISABLED=1)"
    return 0
  fi
  local instance="${PSC_INSTANCE:-paulshaclaw}"
  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "manager service skipped: systemctl --user unavailable (WSL no user systemd?)" >&2
    return 0
  fi
  # #155: timer unit 若未從 deploy/templates 實例化到 ~/.config/systemd/user，
  # 直接 `systemctl start` 會 Unit-not-found。首次啟動先跑 installer
  # （render→daemon-reload→enable --now）；已安裝則不重裝，只 toggle。
  local installer="${PSC_MANAGER_INSTALLER:-${script_dir:-.}/coordinator/install-manager-units.sh}"
  if [[ ! -f "$HOME/.config/systemd/user/${instance}-manager.timer" ]]; then
    echo "manager timer unit 未安裝，執行 install-manager-units.sh ..."
    if ! "${installer}" "${instance}"; then
      echo "manager units install failed (non-fatal)" >&2
      return 0
    fi
  fi
  if systemctl --user start "${instance}-manager.timer"; then
    echo "manager timer started (${instance}-manager.timer)"
  else
    echo "manager timer start failed (non-fatal)" >&2
  fi
  return 0
}

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
PYTHONPATH="$REPO" "$PY" -m paulshaclaw.monitor 200>&- >> ~/.agents/log/monitor.log 2>&1 &
MONITOR_PID=$!
echo "monitor pid=$MONITOR_PID"

if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
  wait "$MONITOR_PID" 2>/dev/null || true
  echo "monitor exited before startup" >&2
  exit 1
fi

# Stagger heavy service startups so their interpreter/import bursts do not all
# land on the same second and recreate the boot-time memory spike.
sleep 2

# Stage 2: memory dream loop (bound to this start.sh lifecycle)
start_dream_loop
start_manager_loop

run_telegram_listener_once() {
  local telegram_listener_pid=""
  trap 'if [[ -n "${telegram_listener_pid:-}" ]]; then kill -TERM "$telegram_listener_pid" 2>/dev/null || true; wait "$telegram_listener_pid" 2>/dev/null || true; fi; exit 143' INT TERM

  mkdir -p "$(dirname "$TELEGRAM_READY_FILE")"
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

if [[ "$telegram_token_present" -eq 1 && "$telegram_config_present" -eq 1 && "$telegram_config_readable" -eq 1 ]]; then
  mkdir -p "$(dirname "$TELEGRAM_READY_FILE")"
  : > "$TELEGRAM_READY_FILE"
  export PSC_TELEGRAM_READY_FILE="$TELEGRAM_READY_FILE"
  export PSC_BOT_SUPERVISOR_LOG="$TELEGRAM_LOG"
  start_bot_supervised run_telegram_listener_once
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

# Keep the cockpit launch off the telegram/monitor startup second as well so
# the last large TUI process does not stack onto the same burst.
sleep 2

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
PYTHONPATH="$REPO" "$PY" -m paulshaclaw.cockpit --cockpit-pane "${TMUX_PANE:?must run inside tmux}" < "$_cockpit_stdin" 200>&- &
COCKPIT_PID=$!
if wait "$COCKPIT_PID"; then
  exit 0
else
  cockpit_status=$?
  exit "$cockpit_status"
fi
