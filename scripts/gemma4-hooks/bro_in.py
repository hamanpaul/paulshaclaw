#!/usr/bin/env python3
"""UserPromptSubmit hook: stash the source Telegram user_id for [bro:<id>] prompts."""
from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from paulshaclaw.config import paths

BRO_RE = re.compile(r"^\s*\[bro:(\d+)\]")
DEFAULT_STATE_DIR = paths.state_path("bro-hook")
LOG = paths.log_root() / "bro-hook.log"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} bro_in {stage}: {exc!r}\n")
    except Exception:
        pass


def handle(event: dict, state_dir: Path) -> None:
    session_id = str(event.get("session_id") or "").strip()
    if not session_id:
        return
    sf = state_dir / f"{session_id}.json"
    match = BRO_RE.match(event.get("prompt") or "")
    if match:
        state_dir.mkdir(parents=True, exist_ok=True)
        sf.write_text(
            json.dumps({"user_id": int(match.group(1)), "ts": datetime.datetime.now().isoformat()}),
            encoding="utf-8",
        )
    else:
        sf.unlink(missing_ok=True)


def main() -> int:
    try:
        handle(json.load(sys.stdin), DEFAULT_STATE_DIR)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
