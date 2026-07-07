#!/usr/bin/env python3
"""Stop hook: relay the turn's final assistant text to the bro Telegram user."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from paulshaclaw.config import paths

DEFAULT_STATE_DIR = paths.state_path("bro-hook")
REPLY_BRIDGE = paths.agents_path("skills", "bro", "scripts", "reply_bridge.py")
LOG = paths.log_root() / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"
# At Stop-hook time the current turn's assistant record may not be flushed to the
# transcript yet. Poll briefly for it rather than grabbing the previous turn's
# reply (the "回到前一次的回覆" off-by-one).
REPLY_WAIT_SECONDS = 5.0
REPLY_POLL_INTERVAL = 0.2


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} bro_out {stage}: {exc!r}\n")
    except Exception:
        pass


def _assistant_text(rec: dict) -> str:
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    if isinstance(content, str):
        return content
    return ""


def current_turn_reply(transcript_path: Path) -> tuple[bool, str]:
    """Return (has_reply, text) for the CURRENT turn — the assistant text that
    appears AFTER the last user-role record.

    `has_reply` is False when no assistant record has been written past the last
    user message yet (this turn's reply hasn't been flushed to the transcript),
    letting callers wait instead of sending the previous turn's reply. Scanning
    after the last user record also handles tool turns (the final answer follows
    the last tool_result, which is itself a user-role record)."""
    records = []
    for line in transcript_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") in ("user", "assistant"):
            records.append(rec)
    last_user = -1
    for index, rec in enumerate(records):
        if rec.get("type") == "user":
            last_user = index
    after = [rec for rec in records[last_user + 1:] if rec.get("type") == "assistant"]
    text = "".join(_assistant_text(rec) for rec in after).strip()
    return bool(after), text


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


def handle(event: dict, state_dir: Path, sender=_send_via_bridge, wait_seconds: float = REPLY_WAIT_SECONDS) -> bool:
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
        transcript = Path(tp)
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            try:
                has_reply, text = current_turn_reply(transcript)
            except Exception as exc:
                _log("transcript", exc)
                break
            if has_reply or time.monotonic() >= deadline:
                break
            time.sleep(REPLY_POLL_INTERVAL)
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
