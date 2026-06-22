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

exit 0
