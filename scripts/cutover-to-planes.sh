#!/usr/bin/env bash
# cutover-to-planes.sh —— 把一台機器更新/移植到「operator shell + 外部平面」形態：
#   一併裝設 paulsha-hippo（記憶平面）與 paulsha-cortex（治理平面）並完成服務 cutover。
#
# 做什麼：
#   1. git pull 主 repo 到 main（operator shell、已刪 5 包、pin 外部平面）
#   2. 建立/刷新 repo .venv，並依 pyproject pin 強制重裝完整 operator runtime
#   3. 用 pipx 持久安裝 paulsha-hippo（記憶）與 paulsha-cortex（治理）
#   4. hippo：init + install hooks + install service（dream 常駐）
#   5. 停用舊 paulshaclaw-manager / demo-manager 單元（cutover 先停舊）
#   6. cortex install service + enable（manager + monitor 一次帶）
#   7. 確保 monitor 有 project 設定（否則起不來）
#   8. 健檢：hippo doctor + cortex 服務 active + F1 自停 gate
#
# 冪等：可重跑。無 user systemd（如某些 WSL）：走前景 fallback，並於報告標 N/A。
# runtime 狀態（~/.agents/control、~/.agents/memory）零遷移沿用。
set -euo pipefail

systemd_ok() {
  command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1
}

install_operator_runtime() {
  local repo="${1:?repo root is required}"
  local bootstrap_python venv_python
  bootstrap_python="$(command -v python3 2>/dev/null || true)"
  [[ -n "$bootstrap_python" ]] || return 1
  "$bootstrap_python" -m venv "$repo/.venv" || return 1
  venv_python="$repo/.venv/bin/python"
  [[ -x "$venv_python" ]] || return 1
  "$venv_python" -m pip install --upgrade --force-reinstall -e "$repo"
}

pin_of() {
  local repo="${1:?repo root is required}"
  local package="${2:?package is required}"
  grep -m1 -oE "$package@[0-9a-f]{40}" "$repo/pyproject.toml"
}

install_plane_clis() {
  local repo="${1:?repo root is required}"
  local hippo_pin cortex_pin
  hippo_pin="$(pin_of "$repo" paulsha-hippo)" || return 1
  cortex_pin="$(pin_of "$repo" paulsha-cortex)" || return 1
  [[ -n "$hippo_pin" && -n "$cortex_pin" ]] || return 1
  command -v pipx >/dev/null 2>&1 || return 1
  pipx install "git+https://github.com/hamanpaul/${hippo_pin}" --force || return 1
  pipx install "git+https://github.com/hamanpaul/${cortex_pin}" --force
}

install_cortex_service_units() {
  local instance="${1:?instance is required}"
  local repo="${2:?repo root is required}"
  command -v cortex >/dev/null 2>&1 || return 1
  cortex install service --instance "$instance" --repo-root "$repo"
}

initialize_hippo() {
  command -v hippo >/dev/null 2>&1 || return 1
  hippo init || return 1
  hippo install hooks
}

install_hippo_service() {
  command -v hippo >/dev/null 2>&1 || return 1
  hippo install service
}

retire_legacy_services() {
  local unit active_state enabled_state
  local -a units=(
    paulshaclaw-manager.timer
    paulshaclaw-manager.service
    demo-manager.timer
    demo-manager.service
  )
  for unit in "${units[@]}"; do
    systemctl --user stop "$unit" 2>/dev/null || true
    systemctl --user disable "$unit" 2>/dev/null || true
  done
  systemctl --user daemon-reload >/dev/null || return 1
  for unit in "${units[@]}"; do
    active_state="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
    enabled_state="$(systemctl --user is-enabled "$unit" 2>/dev/null || true)"
    [[ "$active_state" == "inactive" || "$active_state" == "unknown" ]] || return 1
    [[ "$enabled_state" == "disabled" || "$enabled_state" == "not-found" ]] || return 1
  done
}

ensure_monitor_project_config() {
  local config_root="${1:?config root is required}"
  local legacy_config="${2:?legacy config is required}"
  local workspace_root="${3:?workspace root is required}"
  local project_config="$config_root/project-cortex.yaml"
  mkdir -p "$config_root" || return 1
  if [[ ! -f "$project_config" && ! -f "$legacy_config" ]]; then
    cat > "$project_config" <<YAML
workspaces:
  - name: prj
    path: $workspace_root
YAML
  fi
}

restart_monitor_service() {
  local instance="${1:?instance is required}"
  systemctl --user restart "${instance}-monitor.service" 2>/dev/null || return 1
  systemctl --user is-active --quiet "${instance}-monitor.service" 2>/dev/null
}

enable_and_verify_cortex_services() {
  local instance="${1:?instance is required}"
  local settle="${PSC_CUTOVER_SETTLE_SECONDS:-}"
  systemctl --user reset-failed "${instance}-manager.service" "${instance}-monitor.service" || return 1
  systemctl --user enable --now "${instance}-manager.timer" "${instance}-monitor.service" || return 1
  restart_monitor_service "$instance" || return 1
  sleep "${settle:-2}"
  systemctl --user is-active --quiet "${instance}-monitor.service" 2>/dev/null || return 1
  systemctl --user restart "${instance}-manager.service" 2>/dev/null || return 1
  sleep "${settle:-3}"
  systemctl --user is-active --quiet "${instance}-manager.service" 2>/dev/null
}

if [[ "${1:-}" == "--source-only" ]]; then
  return 0 2>/dev/null || exit 0
fi

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTANCE="${PSC_INSTANCE:-cortex}"
log() { printf '\033[36m[cutover]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[cutover]\033[0m %s\n' "$*" >&2; }

# --- 1. 主 repo 到 main ---
log "更新主 repo（$REPO）到 main"
if ! git -C "$REPO" checkout main || ! git -C "$REPO" pull --ff-only; then
  warn "主 repo 更新失敗——停止 cutover"
  exit 1
fi

# --- 2. 建立/刷新 operator runtime（PEP 668-safe；force 對齊同版本 VCS pin）---
log "建立/刷新 operator runtime（$REPO/.venv）"
if ! install_operator_runtime "$REPO"; then
  warn "operator runtime 安裝失敗——請確認 python3-venv 與網路後重跑"
  exit 1
fi

# --- 3. 依 pyproject pin 持久安裝 hippo + cortex（public，免認證）---
if ! command -v pipx >/dev/null 2>&1; then
  warn "pipx 未安裝——Ubuntu/Debian 請先用套件管理器安裝 'sudo apt install pipx'，再執行 pipx ensurepath"
  exit 1
fi
log "依 pyproject pins 用 pipx 安裝 hippo + cortex"
if ! install_plane_clis "$REPO"; then
  warn "pipx 安裝 hippo/cortex 失敗——停止 cutover"
  exit 1
fi

# --- 4. hippo：init + hooks + dream service ---
log "hippo init / install hooks"
if ! initialize_hippo; then
  warn "hippo CLI 缺失或 init/hooks 安裝失敗——停止 cutover"
  exit 1
fi
if systemd_ok; then
  log "hippo install service（dream）"
  if ! install_hippo_service; then
    warn "hippo service 安裝失敗——停止 cutover"
    exit 1
  fi
else
  install_hippo_service || warn "systemd N/A：hippo service 安裝非零，交由前景 fallback"
fi

# --- 5. 停用舊 manager/monitor 單元（cutover 先停舊）---
if systemd_ok; then
  if ! retire_legacy_services; then
    warn "legacy manager units 除役驗證失敗——停止 cutover"
    exit 1
  fi
else
  warn "systemd 不可用：殺前景舊 manager/monitor 進程"
  pkill -f 'paulshaclaw.coordinator.manager_daemon' 2>/dev/null || true
  pkill -f 'paulshaclaw.monitor' 2>/dev/null || true
fi

# --- 6. cortex install service + enable（manager + monitor）---
log "cortex install service --instance $INSTANCE --repo-root $REPO"
if ! install_cortex_service_units "$INSTANCE" "$REPO"; then
  warn "cortex service unit 安裝失敗——停止 cutover"
  exit 1
fi

# --- 7. monitor project 設定（缺則 monitor 起不來）---
CFG_ROOT="${PSC_PROJECT_CONFIG_ROOT:-$HOME/.agents/config/paulsha}"
LEGACY_CFG="$HOME/.config/paulshaclaw/paulshaclaw.yaml"
if [[ ! -f "$CFG_ROOT/project-cortex.yaml" && ! -f "$LEGACY_CFG" ]]; then
  warn "無 monitor project 設定——寫入樣板 $CFG_ROOT/project-cortex.yaml（請按實際 workspace 調整）"
elif [[ -f "$LEGACY_CFG" && ! -f "$CFG_ROOT/project-cortex.yaml" ]]; then
  log "沿用 legacy monitor 設定 $LEGACY_CFG（建議日後遷至 $CFG_ROOT/project-cortex.yaml）"
fi
if ! ensure_monitor_project_config "$CFG_ROOT" "$LEGACY_CFG" "$HOME/prj_pri"; then
  warn "monitor project 設定建立失敗——停止 cutover"
  exit 1
fi

# --- 8. enable + start + F1 gate 健檢 ---
if systemd_ok; then
  if ! enable_and_verify_cortex_services "$INSTANCE"; then
    warn "cortex systemd enable/restart/active gate 失敗——停止 cutover"
    exit 1
  fi
  log "✅ ${INSTANCE}-manager active（F1 未自停）"
  log "monitor: active"
  command -v hippo >/dev/null 2>&1 && hippo doctor 2>&1 | sed 's/^/  hippo doctor: /' | tail -6 || true
else
  warn "systemd N/A：cortex 服務改前景 supervise（見 start.sh fallback）；本腳本不常駐前景"
fi

log "cutover 完成。runtime 狀態（~/.agents/control、~/.agents/memory）零遷移沿用。"
