#!/usr/bin/env bash
# Shared session_start/stop relay hook. Best-effort only: relay failures must not
# affect agent execution or completion detection.
set -u

slice="${PSC_SLICE_ID:-unknown}"
event="${PSC_RELAY_EVENT:-unknown}"
target="${PSC_RELAY_TARGET:-}"
msg="[manager] slice=${slice} event=${event}"

if [[ -n "$target" ]]; then
  printf '%s\n' "$msg" >>"$target" 2>/dev/null || true
fi

# #120 Half 1: 僅 manager 派工（launcher 注入 PSC_SLICE_ID）才推 Telegram；
# 互動 session 無 slice → no-op，避免灌爆。broadcast（不帶 --source-user-id）。
reply_bridge="${PSC_REPLY_BRIDGE:-$HOME/.agents/skills/bro/scripts/reply_bridge.py}"
if [[ "$slice" != "unknown" && -f "$reply_bridge" ]]; then
  python3 "$reply_bridge" --text "$msg" >/dev/null 2>&1 || true
fi

exit 0
