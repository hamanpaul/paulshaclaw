#!/usr/bin/env bash
# 安裝 persona manager systemd --user units（render→copy→daemon-reload→enable）。
# 用法：install-manager-units.sh [instance] [interval_seconds]
set -euo pipefail

INSTANCE="${1:-${PSC_INSTANCE:-paulshaclaw}}"
INTERVAL="${2:-${PSC_MANAGER_INTERVAL_SECONDS:-300}}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TPL="$REPO/paulshaclaw/deploy/templates/core/systemd"
UNIT_DIR="$HOME/.config/systemd/user"
RUNTIME_DIR="$HOME/.agents/core/runtime"

mkdir -p "$UNIT_DIR" "$RUNTIME_DIR" "$HOME/.agents/specs"

render() {  # $1=template $2=target
  sed -e "s/__INSTANCE__/${INSTANCE}/g" \
      -e "s/^OnUnitActiveSec=.*/OnUnitActiveSec=${INTERVAL}/" \
      "$1" > "$2"
}

render "$TPL/__INSTANCE__-manager.service.tmpl" "$UNIT_DIR/${INSTANCE}-manager.service"
render "$TPL/__INSTANCE__-manager.timer.tmpl"   "$UNIT_DIR/${INSTANCE}-manager.timer"
render "$REPO/paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl" \
       "$RUNTIME_DIR/${INSTANCE}-manager.env"
# 注入 PYTHONPATH=$REPO，讓 source-checkout（非 pip 安裝）下 systemd 跑得起
# `python3 -m paulshaclaw.coordinator`（review F-B）。
echo "PYTHONPATH=$REPO" >> "$RUNTIME_DIR/${INSTANCE}-manager.env"

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable --now "${INSTANCE}-manager.timer"
  echo "installed + enabled ${INSTANCE}-manager.timer (interval=${INTERVAL}s)"
else
  echo "units rendered but systemctl --user unavailable; 需在有 user systemd 的 session 內 enable" >&2
fi

if command -v loginctl >/dev/null 2>&1 && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
  echo "提示：開機自啟需 'loginctl enable-linger $USER'（WSL 尤需）" >&2
fi
