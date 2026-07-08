#!/usr/bin/env bash
# cutover-to-cortex.sh —— 把一台機器的 paulshaclaw 更新/移植到「operator shell + 外部 hippo/cortex 平面」形態。
#
# 做什麼：
#   1. git pull 主 repo 到 main（operator shell、已刪 5 包、pin 外部平面）
#   2. 依 pyproject 宣告的 pin，用 pipx 持久安裝 paulsha-hippo（記憶）與 paulsha-cortex（治理）
#   3. hippo：init + install hooks + install service（dream 常駐）
#   4. 停用舊 paulshaclaw-manager / demo-manager 單元（cutover 先停舊）
#   5. cortex install service + enable（manager + monitor 一次帶）
#   6. 確保 monitor 有 project 設定（否則起不來）
#   7. 健檢：hippo doctor + cortex 服務 active + F1 自停 gate
#
# 冪等：可重跑。無 user systemd（如某些 WSL）：走前景 fallback，並於報告標 N/A。
# runtime 狀態（~/.agents/control、~/.agents/memory）零遷移沿用。
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTANCE="${PSC_INSTANCE:-cortex}"
log() { printf '\033[36m[cutover]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[cutover]\033[0m %s\n' "$*" >&2; }
systemd_ok() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }

# --- 1. 主 repo 到 main ---
log "更新主 repo（$REPO）到 main"
git -C "$REPO" checkout main
git -C "$REPO" pull --ff-only

# --- 2. 依 pyproject pin 持久安裝 hippo + cortex（public，免認證）---
pin_of() { grep -oE "$1@[0-9a-f]{40}" "$REPO/pyproject.toml" | head -1; }
HIPPO_PIN="$(pin_of paulsha-hippo)"
CORTEX_PIN="$(pin_of paulsha-cortex)"
if ! command -v pipx >/dev/null 2>&1; then
  warn "pipx 未安裝——請先 'python -m pip install --user pipx && pipx ensurepath'，重開 shell 後再跑"
  exit 1
fi
log "pipx 安裝 hippo（git+https://github.com/hamanpaul/$HIPPO_PIN）"
pipx install "git+https://github.com/hamanpaul/${HIPPO_PIN}" --force
log "pipx 安裝 cortex（git+https://github.com/hamanpaul/$CORTEX_PIN）"
pipx install "git+https://github.com/hamanpaul/${CORTEX_PIN}" --force

# --- 3. hippo：init + hooks + dream service ---
if command -v hippo >/dev/null 2>&1; then
  log "hippo init / install hooks / install service（dream）"
  hippo init 2>&1 | sed 's/^/  hippo: /' || warn "hippo init 非零（可能已初始化）"
  hippo install hooks 2>&1 | sed 's/^/  hippo: /' || warn "hippo install hooks 非零"
  hippo install service 2>&1 | sed 's/^/  hippo: /' || warn "hippo install service 非零（systemd 不可用時屬預期）"
else
  warn "hippo CLI 未在 PATH（pipx ensurepath 後重開 shell）"
fi

# --- 4. 停用舊 manager/monitor 單元（cutover 先停舊）---
if systemd_ok; then
  for u in "paulshaclaw-manager.timer" "paulshaclaw-manager.service" "demo-manager.timer" "demo-manager.service"; do
    systemctl --user stop "$u" 2>/dev/null && systemctl --user disable "$u" 2>/dev/null && log "停用舊單元 $u" || true
  done
  systemctl --user daemon-reload 2>/dev/null || true
else
  warn "systemd 不可用：殺前景舊 manager/monitor 進程"
  pkill -f 'paulshaclaw.coordinator.manager_daemon' 2>/dev/null || true
  pkill -f 'paulshaclaw.monitor' 2>/dev/null || true
fi

# --- 5. cortex install service + enable（manager + monitor）---
if command -v cortex >/dev/null 2>&1; then
  log "cortex install service --instance $INSTANCE --repo-root $REPO"
  cortex install service --instance "$INSTANCE" --repo-root "$REPO" 2>&1 | sed 's/^/  cortex: /'
else
  warn "cortex CLI 未在 PATH（pipx ensurepath 後重開 shell）"; exit 1
fi

# --- 6. monitor project 設定（缺則 monitor 起不來）---
CFG_ROOT="${PSC_PROJECT_CONFIG_ROOT:-$HOME/.agents/config/paulsha}"
mkdir -p "$CFG_ROOT"
LEGACY_CFG="$HOME/.config/paulshaclaw/paulshaclaw.yaml"
if [[ ! -f "$CFG_ROOT/project-cortex.yaml" && ! -f "$LEGACY_CFG" ]]; then
  warn "無 monitor project 設定——寫入樣板 $CFG_ROOT/project-cortex.yaml（請按實際 workspace 調整）"
  cat > "$CFG_ROOT/project-cortex.yaml" <<YAML
workspaces:
  - name: prj
    path: $HOME/prj_pri
YAML
elif [[ -f "$LEGACY_CFG" && ! -f "$CFG_ROOT/project-cortex.yaml" ]]; then
  log "沿用 legacy monitor 設定 $LEGACY_CFG（建議日後遷至 $CFG_ROOT/project-cortex.yaml）"
fi

# --- 7. enable + start + F1 gate 健檢 ---
if systemd_ok; then
  systemctl --user reset-failed "${INSTANCE}-manager.service" "${INSTANCE}-monitor.service" 2>/dev/null || true
  systemctl --user enable --now "${INSTANCE}-manager.timer" "${INSTANCE}-monitor.service" 2>&1 | sed 's/^/  systemd: /' || true
  sleep 2
  systemctl --user restart "${INSTANCE}-manager.service" 2>/dev/null || true; sleep 3   # F1 自停 gate
  if systemctl --user is-active --quiet "${INSTANCE}-manager.service"; then
    log "✅ ${INSTANCE}-manager active（F1 未自停）"
  else
    warn "❌ ${INSTANCE}-manager 未 active——若為自停，確認 cortex pin 已含 F1 修正（issue #2）"
  fi
  log "monitor: $(systemctl --user is-active "${INSTANCE}-monitor.service" 2>/dev/null)"
  command -v hippo >/dev/null 2>&1 && hippo doctor 2>&1 | sed 's/^/  hippo doctor: /' | tail -6 || true
else
  warn "systemd N/A：cortex 服務改前景 supervise（見 start.sh fallback）；本腳本不常駐前景"
fi

log "cutover 完成。runtime 狀態（~/.agents/control、~/.agents/memory）零遷移沿用。"
