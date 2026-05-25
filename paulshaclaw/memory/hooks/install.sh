#!/usr/bin/env bash
# install.sh — memory importer hook installer
#
# Modes:
#   --tree-only   Create the memory directory tree only (no hooks, no config)
#   (default)     Full install: tree + venv + hook scripts + config files
#
# Options:
#   --memory-root PATH    Override memory root (default: ~/.agents/memory)
#   --config-root PATH    Override config root (default: ~); used for .claude / .codex / .copilot
#   --repo-root   PATH    Override repo root (default: git rev-parse --show-toplevel)
#   --skip-venv           Skip venv creation and pip install (useful for tests)
set -euo pipefail

memory_root="${HOME}/.agents/memory"
config_root="${HOME}"
repo_root=""
tree_only=false
skip_venv=false

while (($#)); do
  case "$1" in
    --tree-only)
      tree_only=true
      shift
      ;;
    --memory-root)
      if (($# < 2)); then
        echo "install.sh: --memory-root requires a path" >&2
        exit 2
      fi
      memory_root="$2"
      shift 2
      ;;
    --config-root)
      if (($# < 2)); then
        echo "install.sh: --config-root requires a path" >&2
        exit 2
      fi
      config_root="$2"
      shift 2
      ;;
    --repo-root)
      if (($# < 2)); then
        echo "install.sh: --repo-root requires a path" >&2
        exit 2
      fi
      repo_root="$2"
      shift 2
      ;;
    --skip-venv)
      skip_venv=true
      shift
      ;;
    *)
      echo "install.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

repo_root_file="${memory_root}/hooks/repo-root.txt"

# Validate memory_root
if [[ "$memory_root" =~ ^[[:space:]]*$ ]]; then
  echo "install.sh: --memory-root must not be empty" >&2
  exit 2
fi

if [[ "$memory_root" =~ ^/+$ ]]; then
  echo "install.sh: --memory-root must not be /" >&2
  exit 2
fi

# Resolve repo_root if not provided
if [[ -z "$repo_root" ]]; then
  if git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel &>/dev/null; then
    repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
  elif [[ -f "$repo_root_file" ]]; then
    repo_root="$(<"$repo_root_file")"
  else
    echo "install.sh: cannot determine repo root; pass --repo-root" >&2
    exit 2
  fi
fi

# ------------------------------------------------------------------
# Step 1: Create memory tree (shared between tree-only and full install)
# ------------------------------------------------------------------
dirs=(
  "inbox"
  "work-centric"
  "knowledge"
  "runtime"
  "log"
  "hooks"
  "archive"
  "inbox/sessions"
  "inbox/plans"
  "inbox/research"
  "inbox/reports"
  "work-centric/common-sense"
  "runtime/queue"
  "runtime/queue/_failed"
  "runtime/locks"
  "runtime/ledger"
  "runtime/indexes"
  "archive/queue"
)

for relative in "${dirs[@]}"; do
  path="${memory_root}/${relative}"
  install -d -m 700 -- "$path"
  touch -- "${path}/.gitkeep"
done

printf '%s\n' "$repo_root" >"$repo_root_file"
chmod 600 "$repo_root_file"

if [[ "$tree_only" == true ]]; then
  exit 0
fi

# ------------------------------------------------------------------
# Step 2: Venv + editable install (skip if --skip-venv)
# ------------------------------------------------------------------
venv_dir="${memory_root}/hooks/.venv"

if [[ "$skip_venv" != true ]]; then
  if python3 -m venv --help &>/dev/null 2>&1; then
    python3 -m venv "$venv_dir"
    "${venv_dir}/bin/pip" install --quiet -e "${repo_root}"
  else
    echo "install.sh: WARN python3 venv unavailable; skipping venv creation" >&2
  fi
fi

# ------------------------------------------------------------------
# Step 3: Deploy hook scripts
# ------------------------------------------------------------------
hooks_src_dir="${repo_root}/paulshaclaw/memory/hooks"

for script in install.sh uninstall.sh claude_session_end.py codex_session_end.py copilot_session_end.py; do
  src="${hooks_src_dir}/${script}"
  dst="${memory_root}/hooks/${script}"
  if [[ -f "$src" ]]; then
    install -m 700 -- "$src" "$dst"
  else
    echo "install.sh: WARN hook source not found: ${src}" >&2
  fi
done

# ------------------------------------------------------------------
# Helper: determine venv python path for config templates
# ------------------------------------------------------------------
if [[ "$skip_venv" == true ]]; then
  venv_python="${venv_dir}/bin/python"
else
  venv_python="${venv_dir}/bin/python"
fi
hook_dir="${memory_root}/hooks"

# ------------------------------------------------------------------
# Step 4: Claude settings.json — merge SessionEnd hook entry
# ------------------------------------------------------------------
claude_settings="${config_root}/.claude/settings.json"
install -d -m 700 "$(dirname "$claude_settings")"

# Build the hook entry we manage (use a sentinel comment-free marker in command)
claude_hook_command="${venv_python} ${hook_dir}/claude_session_end.py"

# Read existing JSON or start fresh
if [[ -f "$claude_settings" ]]; then
  existing_claude="$(cat "$claude_settings")"
else
  existing_claude="{}"
fi

python3 - "$claude_settings" "$existing_claude" "$claude_hook_command" <<'PYEOF'
import json, sys

settings_path = sys.argv[1]
existing_json = sys.argv[2]
hook_command = sys.argv[3]

try:
    settings = json.loads(existing_json)
except Exception:
    settings = {}

hooks = settings.setdefault("hooks", {})
session_end_list = hooks.setdefault("SessionEnd", [])

# Check if our managed entry already present (match by command substring)
managed_marker = "claude_session_end.py"
already = any(
    any(managed_marker in h.get("command", "")
        for h in entry.get("hooks", []))
    for entry in session_end_list
)

if not already:
    session_end_list.append({
        "matcher": "",
        "hooks": [{
            "type": "command",
            "command": hook_command,
            "timeout": 10,
        }]
    })
    settings["hooks"]["SessionEnd"] = session_end_list

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF

# ------------------------------------------------------------------
# Step 5: Codex hooks.json — merge Stop / SubagentStop entries
# ------------------------------------------------------------------
codex_hooks="${config_root}/.codex/hooks.json"
install -d -m 700 "$(dirname "$codex_hooks")"

codex_stop_command="${venv_python} ${hook_dir}/codex_session_end.py"
codex_subagent_command="${venv_python} ${hook_dir}/codex_session_end.py --subagent"

if [[ -f "$codex_hooks" ]]; then
  existing_codex="$(cat "$codex_hooks")"
else
  existing_codex="{}"
fi

python3 - "$codex_hooks" "$existing_codex" "$codex_stop_command" "$codex_subagent_command" <<'PYEOF'
import json, sys

codex_path = sys.argv[1]
existing_json = sys.argv[2]
stop_command = sys.argv[3]
subagent_command = sys.argv[4]

try:
    data = json.loads(existing_json)
except Exception:
    data = {}

hooks = data.setdefault("hooks", {})

def _has_managed(event_list, marker):
    return any(
        any(marker in h.get("command", "")
            for h in entry.get("hooks", []))
        for entry in event_list
    )

def _managed_entry(command, status_msg):
    return {
        "matcher": ".*",
        "hooks": [{"type": "command", "command": command, "statusMessage": status_msg}]
    }

stop_list = hooks.setdefault("Stop", [])
if not _has_managed(stop_list, "codex_session_end.py"):
    stop_list.append(_managed_entry(stop_command, "paulsha-memory: capturing turn snapshot"))

subagent_list = hooks.setdefault("SubagentStop", [])
if not _has_managed(subagent_list, "--subagent"):
    subagent_list.append(_managed_entry(subagent_command, "paulsha-memory: capturing subagent snapshot"))

with open(codex_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF

# ------------------------------------------------------------------
# Step 6: Copilot hook config — write paulsha-memory.json
# ------------------------------------------------------------------
copilot_hook="${config_root}/.copilot/hooks/paulsha-memory.json"
install -d -m 700 "$(dirname "$copilot_hook")"

copilot_command="${venv_python} ${hook_dir}/copilot_session_end.py"

python3 - "$copilot_hook" "$copilot_command" <<'PYEOF'
import json, sys

hook_path = sys.argv[1]
bash_command = sys.argv[2]

config = {
    "version": 1,
    "hooks": {
        "sessionEnd": [
            {
                "type": "command",
                "bash": bash_command,
                "powershell": "Write-Host 'paulsha-memory: powershell path not supported in MVP'",
                "timeoutSec": 10,
            }
        ]
    }
}

with open(hook_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF

# ------------------------------------------------------------------
# Step 7: Write projects.yaml (only if absent)
# ------------------------------------------------------------------
projects_yaml="${config_root}/.agents/config/projects.yaml"
install -d -m 700 "$(dirname "$projects_yaml")"

if [[ ! -f "$projects_yaml" ]]; then
  sample_yaml="${repo_root}/config/agents-projects.sample.yaml"
  if [[ -f "$sample_yaml" ]]; then
    install -m 600 "$sample_yaml" "$projects_yaml"
  else
    echo "install.sh: WARN sample projects yaml not found: ${sample_yaml}" >&2
  fi
fi

# ------------------------------------------------------------------
# Done — print Codex /hooks trust reminder
# ------------------------------------------------------------------
echo ""
echo "paulsha-memory install complete."
echo ""
echo "  IMPORTANT (Codex): Run '/hooks' inside Codex CLI to review and trust"
echo "  the newly installed hook scripts. Hook script changes invalidate trust"
echo "  automatically and will require re-review."
echo ""
