#!/usr/bin/env bash
# uninstall.sh — remove managed paulsha-memory hook config entries
#
# Removes:
#   - The managed SessionEnd entry from ~/.claude/settings.json
#   - The managed Stop/SubagentStop entries from ~/.codex/hooks.json
#   - The entire ~/.copilot/hooks/paulsha-memory.json file
#
# Preserves:
#   - inbox content, projects.yaml, and all other memory tree contents
#   - Unrelated keys/entries in claude settings.json and codex hooks.json
#
# Options:
#   --memory-root PATH    (unused here but accepted for script symmetry)
#   --config-root PATH    Override config root (default: ~)
set -euo pipefail

config_root="${HOME}"
# memory_root accepted but not currently needed; kept for CLI symmetry
memory_root="${HOME}/.agents/memory"

while (($#)); do
  case "$1" in
    --config-root)
      if (($# < 2)); then
        echo "uninstall.sh: --config-root requires a path" >&2
        exit 2
      fi
      config_root="$2"
      shift 2
      ;;
    --memory-root)
      if (($# < 2)); then
        echo "uninstall.sh: --memory-root requires a path" >&2
        exit 2
      fi
      memory_root="$2"
      shift 2
      ;;
    *)
      echo "uninstall.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# ------------------------------------------------------------------
# Remove managed Claude SessionEnd hook entry
# ------------------------------------------------------------------
claude_settings="${config_root}/.claude/settings.json"

if [[ -f "$claude_settings" ]]; then
  python3 - "$claude_settings" <<'PYEOF'
import json, sys

settings_path = sys.argv[1]
try:
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
except Exception:
    sys.exit(0)

managed_marker = "claude_session_end.py"

def _is_managed_claude_hook(hook):
    if not isinstance(hook, dict):
        return False
    if hook.get("managedBy") == "paulsha-memory":
        return True
    if hook.get("type") != "command" or hook.get("timeout") != 10:
        return False
    command = hook.get("command")
    if not isinstance(command, str):
        return False
    parts = command.strip().split()
    return (
        len(parts) == 2
        and parts[0].endswith("/hooks/.venv/bin/python")
        and parts[1].endswith(f"/hooks/{managed_marker}")
    )

session_end_list = settings.get("hooks", {}).get("SessionEnd", [])
filtered = []
for entry in session_end_list:
    if not isinstance(entry, dict):
        filtered.append(entry)
        continue
    hooks_list = entry.get("hooks", [])
    if not isinstance(hooks_list, list):
        hooks_list = []
    kept_hooks = [
        hook
        for hook in hooks_list
        if not _is_managed_claude_hook(hook)
    ]
    if kept_hooks:
        updated_entry = dict(entry)
        updated_entry["hooks"] = kept_hooks
        filtered.append(updated_entry)
settings.setdefault("hooks", {})["SessionEnd"] = filtered

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF
fi

# ------------------------------------------------------------------
# Remove managed Codex Stop / SubagentStop hook entries
# ------------------------------------------------------------------
codex_hooks="${config_root}/.codex/hooks.json"

if [[ -f "$codex_hooks" ]]; then
  python3 - "$codex_hooks" <<'PYEOF'
import json, sys

codex_path = sys.argv[1]
try:
    with open(codex_path, encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(0)

def _remove_managed(event_list, marker):
    def _is_managed_codex_hook(hook):
        if not isinstance(hook, dict):
            return False
        if hook.get("managedBy") == "paulsha-memory":
            return True
        if hook.get("type") != "command":
            return False
        status_msg = hook.get("statusMessage")
        if not isinstance(status_msg, str) or not status_msg.startswith("paulsha-memory:"):
            return False
        command = hook.get("command")
        if not isinstance(command, str):
            return False
        parts = command.strip().split()
        return (
            len(parts) in {2, 3}
            and parts[0].endswith("/hooks/.venv/bin/python")
            and parts[1].endswith(f"/hooks/{marker}")
            and (len(parts) == 2 or parts[2] == "--subagent")
        )

    filtered = []
    for entry in event_list:
        if not isinstance(entry, dict):
            filtered.append(entry)
            continue
        hooks_list = entry.get("hooks", [])
        if not isinstance(hooks_list, list):
            hooks_list = []
        kept_hooks = [
            hook
            for hook in hooks_list
            if not _is_managed_codex_hook(hook)
        ]
        if kept_hooks:
            updated_entry = dict(entry)
            updated_entry["hooks"] = kept_hooks
            filtered.append(updated_entry)
    return filtered

hooks = data.get("hooks", {})
if "Stop" in hooks:
    hooks["Stop"] = _remove_managed(hooks["Stop"], "codex_session_end.py")
if "SubagentStop" in hooks:
    hooks["SubagentStop"] = _remove_managed(hooks["SubagentStop"], "codex_session_end.py")

with open(codex_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF
fi

# ------------------------------------------------------------------
# Remove Copilot paulsha-memory.json
# ------------------------------------------------------------------
copilot_hook="${config_root}/.copilot/hooks/paulsha-memory.json"
if [[ -f "$copilot_hook" ]]; then
  rm -f -- "$copilot_hook"
fi

echo "paulsha-memory hooks uninstalled."
