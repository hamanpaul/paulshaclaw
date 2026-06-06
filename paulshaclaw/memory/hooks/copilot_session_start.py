#!/usr/bin/env python3
"""GitHub Copilot CLI sessionStart hook.

Reads stdin camelCase JSON (Copilot sessionStart payload), resolves project from cwd,
builds wake-up brief, and outputs JSON with additionalContext.

Memory root: PSC_MEMORY_ROOT env var (default ~/.agents/memory).
Any exception is logged to log/hooks.log and the script exits 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add repo root to sys.path for imports when running from repo
_hook_file = Path(__file__).resolve()
_repo_root = _hook_file.parents[3]
if _repo_root not in sys.path:
    sys.path.insert(0, str(_repo_root))

TOOL = "copilot-cli"


def main() -> int:
    from paulshaclaw.memory.hooks._wakeup_common import (
        compute_brief,
        log_warn,
        memory_root,
        read_payload,
    )

    root = memory_root()
    payload = read_payload(root, TOOL)

    try:
        # Normalize camelCase cwd
        cwd = payload.get("cwd") or payload.get("workingDirectory")
        brief = compute_brief(root, cwd)

        # Copilot sessionStart shape: additionalContext directly
        output = {
            "additionalContext": brief,
        }
        print(json.dumps(output))
    except Exception as exc:
        log_warn(root, TOOL, f"failed to build output: {exc}")
        # Still print minimal valid output on error
        output = {
            "additionalContext": "",
        }
        print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
