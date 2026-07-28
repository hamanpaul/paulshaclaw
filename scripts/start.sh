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

operator_python_has_runtime() {
  local python="${1:-}"
  local repo="${2:?repo root is required}"
  local probe=$'import paulsha_cortex.cli\nimport paulshaclaw.cost.config\nimport paulshaclaw.cockpit.app\nimport textual'
  [[ -n "$python" && -x "$python" ]] || return 1
  PYTHONPATH="$repo" "$python" -c "$probe" >/dev/null 2>&1
}

cortex_console_python() {
  local cortex_bin shebang python
  cortex_bin="$(command -v cortex 2>/dev/null || true)"
  [[ -n "$cortex_bin" && -r "$cortex_bin" ]] || return 1
  IFS= read -r shebang < "$cortex_bin" || return 1
  [[ "$shebang" == "#!"* ]] || return 1
  python="${shebang#\#!}"
  [[ "$python" == /* && -x "$python" ]] || return 1
  printf '%s\n' "$python"
}

resolve_operator_python() {
  local repo="${1:?repo root is required}"
  local cortex_python=""
  local candidate
  local -a candidates=()

  cortex_python="$(cortex_console_python || true)"
  candidates=(
    "$(command -v "${PSC_PYTHON:-}" 2>/dev/null || true)"
    "$repo/.venv/bin/python"
    "$(command -v python3 2>/dev/null || true)"
    "$cortex_python"
  )
  for candidate in "${candidates[@]}"; do
    if operator_python_has_runtime "$candidate" "$repo"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

ensure_xdg_runtime_dir() {
  # WSL 的非 login shell 常常沒有 XDG_RUNTIME_DIR，`systemctl --user` 因而
  # 「Failed to connect to bus」而被誤判成 systemd 不可用，於是重起一份已在
  # systemd 下常駐的 manager。目錄真的在就把預設值補回來。
  local candidate="${1:-/run/user/$(id -u)}"
  if [[ -n "${XDG_RUNTIME_DIR:-}" ]]; then
    return 0
  fi
  if [[ -d "$candidate" && -w "$candidate" ]]; then
    export XDG_RUNTIME_DIR="$candidate"
  fi
}

cortex_agents_root() {
  printf '%s\n' "${PSC_AGENTS_ROOT:-$HOME/.agents}"
}

cortex_instance() {
  printf '%s\n' "${PSC_INSTANCE:-cortex}"
}

cortex_specs_root() {
  if [[ -n "${PSC_MANAGER_SPECS_DIR:-}" ]]; then
    printf '%s\n' "$PSC_MANAGER_SPECS_DIR"
    return 0
  fi
  if [[ -n "${PSC_SPECS_ROOT:-}" ]]; then
    printf '%s\n' "$PSC_SPECS_ROOT"
    return 0
  fi
  printf '%s/specs\n' "$(cortex_agents_root)"
}

cortex_control_root() {
  if [[ -n "${PSC_CONTROL_ROOT:-}" ]]; then
    printf '%s\n' "$PSC_CONTROL_ROOT"
    return 0
  fi
  printf '%s/control\n' "$(cortex_agents_root)"
}

cortex_tick_interval_seconds() {
  local interval="${PSC_MANAGER_TICK_INTERVAL_SECONDS:-300}"
  if [[ ! "$interval" =~ ^[0-9]+$ ]] || (( interval <= 0 )); then
    interval=300
  fi
  printf '%s\n' "$interval"
}

# manager daemon 以 flock 做 single-instance，所以鎖被持有就代表已有活著的
# manager（systemd 單元或前一輪 fallback）。用 flock 探測而非讀 lock 檔的 pid：
# kernel 的鎖狀態才是真相，crash 留下的陳舊 lock 檔會正確地判為 free。
# `-E 100` 把「拿不到鎖」和其他錯誤分開——只有 100 才算已被持有，開檔失敗等
# 情況維持原本行為（照常嘗試起 daemon，起不來再 fail-closed）。
cortex_manager_lock_is_held() {
  local lock status=0
  lock="$(cortex_control_root)/manager.lock"
  [[ -f "$lock" ]] || return 1
  flock -n -E 100 "$lock" true || status=$?
  if (( status == 100 )); then
    return 0
  fi
  return 1
}

# monitor 沒有 single-instance 保護，第二份會與既有 monitor 搶同一份 state。
cortex_monitor_is_running() {
  local pattern="${PSC_MONITOR_PROC_PATTERN:--m paulsha_cortex.monitor}"
  pgrep -f -- "$pattern" >/dev/null 2>&1
}

# cockpit 啟動前的最後把關：只檢查「本輪 fallback 自己起的」進程。PID 未設代表
# 該角色由 systemd 或既有 daemon 承擔（fallback 刻意跳過），不是啟動失敗。
verify_cortex_fallback_alive() {
  if [[ -n "${CORTEX_MONITOR_PID:-}" ]] && ! kill -0 "$CORTEX_MONITOR_PID" 2>/dev/null; then
    wait "$CORTEX_MONITOR_PID" 2>/dev/null || true
    echo "cortex fallback monitor exited before cockpit start" >&2
    return 1
  fi

  if [[ -n "${CORTEX_MANAGER_PID:-}" ]] && ! kill -0 "$CORTEX_MANAGER_PID" 2>/dev/null; then
    wait "$CORTEX_MANAGER_PID" 2>/dev/null || true
    echo "cortex fallback manager exited before cockpit start" >&2
    return 1
  fi

  return 0
}

ensure_cortex_services() {
  if [[ "${PSC_MANAGER_DISABLED:-0}" == "1" ]]; then
    echo "cortex services disabled (PSC_MANAGER_DISABLED=1)"
    return 0
  fi

  local instance
  instance="$(cortex_instance)"
  local -a install_cmd=(
    "$PY" -m paulsha_cortex.cli install service
    --instance "$instance"
    --repo-root "$REPO"
  )
  local manager_log="$HOME/.agents/log/cortex-manager.log"
  local monitor_log="$HOME/.agents/log/cortex-monitor.log"

  start_cortex_local_fallback() {
    mkdir -p "$HOME/.agents/log"
    mkdir -p "$(cortex_specs_root)"

    if cortex_monitor_is_running; then
      echo "cortex monitor 已在運行，fallback 不重起 monitor" >&2
    else
      PYTHONPATH="$REPO" "$PY" -m paulsha_cortex.cli monitor 200>&- >>"$monitor_log" 2>&1 &
      CORTEX_MONITOR_PID=$!
      if ! kill -0 "$CORTEX_MONITOR_PID" 2>/dev/null; then
        wait "$CORTEX_MONITOR_PID" 2>/dev/null || true
        echo "cortex fallback monitor exited before startup" >&2
        return 1
      fi
    fi

    # F1（對抗審查）：fallback 起「常駐 manager daemon」而非 one-shot tick loop——
    # daemon 才會持 manager.lock、drain ~/.agents/control/requests、寫 manager status；
    # one-shot tick 不持鎖不 drain，cockpit t / Telegram /manager tick 的請求永不被消費。
    # F3：鎖已被持有代表 manager 正常運作中，不是啟動失敗——再起一份只會搶不到鎖
    # 而靜默退出，被下方 gate 判成 startup 失敗並拖垮整個 start.sh。
    if cortex_manager_lock_is_held; then
      echo "cortex manager 已在運行（manager.lock 被持有），fallback 不重起 manager daemon" >&2
    else
      (
        PSC_CONTROL_ROOT="${PSC_CONTROL_ROOT:-$HOME/.agents/control}" \
        PYTHONPATH="$REPO" "$PY" -m paulsha_cortex.coordinator.manager_daemon \
          --specs-dir "$(cortex_specs_root)"
      ) 200>&- >>"$manager_log" 2>&1 &
      CORTEX_MANAGER_PID=$!
      if ! kill -0 "$CORTEX_MANAGER_PID" 2>/dev/null; then
        wait "$CORTEX_MANAGER_PID" 2>/dev/null || true
        echo "cortex fallback manager daemon exited before startup" >&2
        return 1
      fi
    fi

    echo "cortex fallback started (manager daemon pid=${CORTEX_MANAGER_PID:-skipped} monitor pid=${CORTEX_MONITOR_PID:-skipped})" >&2
    return 0
  }

  if ! "${install_cmd[@]}"; then
    echo "cortex install service failed; starting local fallback" >&2
    start_cortex_local_fallback
    return $?
  fi

  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "cortex services installed; systemctl --user unavailable, starting local fallback" >&2
    start_cortex_local_fallback
    return $?
  fi

  # F2（對抗審查）：cutover 順序——啟用 cortex 前先停用舊 paulshaclaw manager 單元，
  # 否則舊 timer 仍 enabled、指向已刪的舊 service 腳本，或與新 manager 搶同一 control root。
  for legacy in paulshaclaw-manager.timer paulshaclaw-manager.service; do
    systemctl --user stop "$legacy" 2>/dev/null || true
    systemctl --user disable "$legacy" 2>/dev/null || true
  done

  if systemctl --user enable --now "${instance}-manager.timer" "${instance}-monitor.service"; then
    echo "cortex services enabled (${instance}-manager.timer ${instance}-monitor.service)"
  else
    echo "cortex services enable/start failed; starting local fallback" >&2
    start_cortex_local_fallback
    return $?
  fi
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

# 必須早於 start_lock：它也吃 XDG_RUNTIME_DIR，晚補會讓同一台機器出現
# /tmp 與 /run/user/<uid> 兩個 lock 路徑，single-instance 保護就破了。
ensure_xdg_runtime_dir

start_lock="${XDG_RUNTIME_DIR:-/tmp}/paulshaclaw-start.lock"
exec 200>"$start_lock"
flock -n 200 || { echo 已有實例在跑; exit 1; }

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$script_dir/.." && pwd)"
# The operator runtime needs both the governance client and the Textual cockpit.
# Prefer PSC_PYTHON, then the repo .venv, system python3, and finally the Python
# from the cortex console-script shebang. A cortex-only pipx venv is rejected.
if ! PY="$(resolve_operator_python "$REPO")"; then
  echo "找不到同時含 paulsha_cortex 與 textual 的 python——請在 repo 執行 'python3 -m venv .venv && .venv/bin/python -m pip install --upgrade --force-reinstall -e .'（或設 PSC_PYTHON 指向具備完整 operator runtime 的 python）" >&2
  exit 1
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

# Extracted service entrypoints. Source-only mode loads function definitions
# without running their standalone main routines.
source "$script_dir/service-cost.sh" --source-only
source "$script_dir/service-dream.sh" --source-only
source "$script_dir/service-bot.sh" --source-only

cleanup() {
  if [[ "${CLEANED_UP:-0}" -eq 1 ]]; then
    return
  fi
  CLEANED_UP=1
  trap - EXIT INT TERM

  for pid in "${TELEGRAM_PID:-}" "${DREAM_PID:-}" "${COCKPIT_PID:-}" "${COST_REFRESH_PID:-}" "${CORTEX_MONITOR_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done

  for pid in "${TELEGRAM_PID:-}" "${DREAM_PID:-}" "${COCKPIT_PID:-}" "${COST_REFRESH_PID:-}" "${CORTEX_MONITOR_PID:-}"; do
    if [[ -n "${pid}" ]]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  if [[ -n "${CORTEX_MANAGER_PID:-}" ]]; then
    kill -TERM "$CORTEX_MANAGER_PID" 2>/dev/null || true
    local shutdown_checks=100
    while (( shutdown_checks > 0 )) && kill -0 "$CORTEX_MANAGER_PID" 2>/dev/null; do
      sleep 0.05
      shutdown_checks=$((shutdown_checks - 1))
    done
    if kill -0 "$CORTEX_MANAGER_PID" 2>/dev/null; then
      kill -KILL "$CORTEX_MANAGER_PID" 2>/dev/null || true
    fi
    wait "$CORTEX_MANAGER_PID" 2>/dev/null || true
  fi
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

apply_stage8_footer
# TMUX guard 在呼叫端（保 main 行為：tmux 外的 dev 啟動不跑 cost loop）；
# systemd 路徑由 service-cost.sh 直跑、不受此限（#219 F2）。
if [[ -n "${TMUX:-}" ]]; then
  start_cost_refresh_loop
fi

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

ensure_cortex_services

# Stagger heavy service startups so their interpreter/import bursts do not all
# land on the same second and recreate the boot-time memory spike.
sleep 2

# Stage 2: memory dream loop (bound to this start.sh lifecycle)
start_dream_loop

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

# Keep the cockpit launch off the prior startup second as well so the last
# large TUI process does not stack onto the same burst.
sleep 2

verify_cortex_fallback_alive || exit 1

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
