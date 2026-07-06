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
  mkdir -p "$HOME/.agents/log"
  local manager_log="$HOME/.agents/log/manager.log"
  (
    PYTHONPATH="$REPO" "$PY" -m paulshaclaw.coordinator.manager_daemon \
      --specs-dir "$REPO/docs/superpowers/specs"
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

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  start_manager_loop
  if [[ -n "${MANAGER_PID:-}" ]]; then
    if [[ "${MANAGER_PID_OWNED:-1}" == "1" ]]; then
      wait "$MANAGER_PID"
    else
      wait_for_manager_shutdown "$MANAGER_PID"
    fi
  fi
fi
