#!/usr/bin/env python3
"""Claude Code PostToolUse(Read) hook: record read-based memory usage attribution.

When a Read targets a path under <memory_root>/knowledge/, append a `used` event
(source="read", offered=bool) to memory_usage.jsonl. Any error -> no event, exit 0.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import _bootstrap  # sibling module; hooks dir is on sys.path[0]

_bootstrap.ensure_repo_on_path()

TOOL = "claude-code"
_SLICE_FM = re.compile(r"^slice_id:\s*(\S+)", re.MULTILINE)
_PROJECT_FM = re.compile(r"^project:\s*(\S+)", re.MULTILINE)


def _frontmatter_field(path: Path, pattern: re.Pattern) -> str:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except Exception:
        return ""
    m = pattern.search(head)
    return m.group(1).strip().strip("'\"") if m else ""


def main() -> int:
    from paulshaclaw.memory.hooks._wakeup_common import (
        log_warn, memory_root, read_payload, sanitize_id,
    )

    root = memory_root()
    payload = read_payload(root, TOOL)
    try:
        if payload.get("tool_name") != "Read":
            return 0
        fp = (payload.get("tool_input") or {}).get("file_path")
        if not fp:
            return 0
        p = Path(fp).resolve()
        knowledge = (root / "knowledge").resolve()
        if knowledge not in p.parents:
            return 0

        session_id = str(payload.get("session_id") or "unknown")
        mpath = root / "runtime" / "wakeup" / f"{TOOL}__{sanitize_id(session_id)}.offered.json"
        by_path = {}
        if mpath.exists():
            try:
                by_path = json.loads(mpath.read_text(encoding="utf-8")).get("by_path", {})
            except Exception:
                by_path = {}

        sl_id = by_path.get(str(p)) or _frontmatter_field(p, _SLICE_FM)
        offered = str(p) in by_path
        project = _frontmatter_field(p, _PROJECT_FM)

        ev = {"ts": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
              "tool": TOOL, "project": project, "sl_id": sl_id, "path": str(p),
              "source": "read", "offered": offered}
        led_dir = root / "runtime" / "ledger"
        led_dir.mkdir(parents=True, exist_ok=True)
        with (led_dir / "memory_usage.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception as exc:
        log_warn(root, TOOL, f"post_tool_use failed: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
