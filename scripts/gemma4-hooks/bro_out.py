#!/usr/bin/env python3
"""Stop hook: relay the turn's final assistant text to the bro Telegram user."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from paulshaclaw.config import paths
from paulshaclaw.core import bro_queue

DEFAULT_STATE_DIR = paths.state_path("bro-hook")
REPLY_BRIDGE = paths.agents_path("skills", "bro", "scripts", "reply_bridge.py")
LOG = paths.log_root() / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"
# At Stop-hook time the current turn's assistant record may not be flushed to the
# transcript yet. Poll briefly for it rather than grabbing the previous turn's
# reply (the "回到前一次的回覆" off-by-one).
REPLY_WAIT_SECONDS = 5.0
REPLY_POLL_INTERVAL = 0.2
# 這個 turn 結束、agent 即將回到 idle 的當下，正是消化 #88 bro-queue 積壓訊息
# 的好時機；一次多試幾筆，把等待期間累積的訊息一口氣送掉。
QUEUE_FLUSH_MAX_ATTEMPTS = 20


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


def _flush_pane_queue() -> None:
    """agent 這個 turn 結束時順手消化自己 pane 的 bro-queue（#88）。

    pane_id 取自 TMUX_PANE：hook 是 claude 的子行程，而 claude 是被
    daemon 用 `tmux send-keys` 打進既有 pane 啟動的，一路繼承下來的
    shell 環境本就會帶這個變數，不用另外傳參數。拿不到就直接跳過——
    這條路徑本來就是 best-effort，不是消化佇列的唯一手段。
    """
    pane_id = os.environ.get("TMUX_PANE", "").strip()
    if not pane_id:
        return
    bro_queue.flush(pane_id, max_attempts=QUEUE_FLUSH_MAX_ATTEMPTS)


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


def handle(
    event: dict,
    state_dir: Path,
    sender=_send_via_bridge,
    wait_seconds: float = REPLY_WAIT_SECONDS,
    queue_flush=_flush_pane_queue,
) -> bool:
    if event.get("stop_hook_active"):
        return False
    try:
        queue_flush()
    except Exception as exc:  # hook 規範：消化佇列失敗只記 log，絕不擋 agent
        _log("queue_flush", exc)
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
