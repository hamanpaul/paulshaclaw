#!/usr/bin/env python3
"""Stop hook: relay the turn's final assistant text to the bro Telegram user."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_STATE_DIR = Path.home() / ".agents" / "state" / "bro-hook"
REPLY_BRIDGE = Path.home() / ".agents" / "skills" / "bro" / "scripts" / "reply_bridge.py"
LOG = Path.home() / ".agents" / "log" / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} bro_out {stage}: {exc!r}\n")
    except Exception:
        pass


def last_assistant_text(transcript_path: Path) -> str:
    text = ""
    for line in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, list):
            joined = "".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
            if joined:
                text = joined
        elif isinstance(content, str) and content.strip():
            text = content.strip()
    return text


def _send_via_bridge(user_id: int, text: str) -> None:
    result = subprocess.run(
        [sys.executable, str(REPLY_BRIDGE), "--source-user-id", str(user_id), "--text", text],
        stdout=subprocess.DEVNULL,  # bridge echoes the full reply; we don't need it buffered
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The reply was lost (unauthorized user, missing binding, Telegram error,
        # …). Record it — silent loss would defeat the relay's observability.
        _log("send", RuntimeError(f"reply_bridge exit {result.returncode}: {(result.stderr or '').strip()[:500]}"))


def handle(event: dict, state_dir: Path, sender=_send_via_bridge) -> bool:
    if event.get("stop_hook_active"):
        return False
    session_id = str(event.get("session_id") or "").strip()
    if not session_id:
        return False
    sf = state_dir / f"{session_id}.json"
    if not sf.exists():
        return False
    try:
        user_id = int(json.loads(sf.read_text(encoding="utf-8"))["user_id"])
    except Exception as exc:
        _log("statefile", exc)
        sf.unlink(missing_ok=True)
        return False
    tp = event.get("transcript_path")
    text = ""
    if tp and Path(tp).exists():
        try:
            text = last_assistant_text(Path(tp))
        except Exception as exc:
            _log("transcript", exc)
    try:
        sender(user_id, text or EMPTY_NOTICE)
    except Exception as exc:
        _log("send", exc)
    sf.unlink(missing_ok=True)
    return True


def main() -> int:
    try:
        handle(json.load(sys.stdin), DEFAULT_STATE_DIR)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
