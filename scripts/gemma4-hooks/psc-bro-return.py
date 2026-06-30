#!/usr/bin/env python3
"""codex Stop / copilot agentStop hook: 把本輪回覆送回 bro Telegram user（turn-scoped）。

turn-scoped：用本輪 user_prompts[-1] 的 [bro:<id>] 自我發現收件 user（無 marker → no-op）。
reply：copilot 取自 read_copilot_history、codex 取自 Stop event payload last_assistant_message。
reply 為 None（讀不到）→ skip 不送；為 "" → 送 EMPTY_NOTICE；hook MUST always exit 0。
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

from paulshaclaw.memory.importer.adapters.base import (
    read_codex_rollout,
    read_copilot_history,
)

BRO_RE = re.compile(r"^\s*\[bro:(\d+)\]")
REPLY_BRIDGE = Path.home() / ".agents" / "skills" / "bro" / "scripts" / "reply_bridge.py"
LOG = Path.home() / ".agents" / "log" / "bro-hook.log"
EMPTY_NOTICE = "（已完成，無文字輸出）"


def _log(stage: str, exc: Exception) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now().isoformat()} psc-bro-return {stage}: {exc!r}\n")
    except Exception:
        pass


def _send_via_bridge(user_id: int, text: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(REPLY_BRIDGE), "--source-user-id", str(user_id), "--text", text],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        _log("send", exc)
        return
    if result.returncode != 0:
        _log("send", RuntimeError(f"reply_bridge exit {result.returncode}: {(result.stderr or '').strip()[:500]}"))


def _discover_user_id(prompts: list[str]) -> int | None:
    """turn-scoped：本輪 = 最後一則 user prompt。無 marker → None。"""
    if not prompts:
        return None
    m = BRO_RE.match(prompts[-1] or "")
    return int(m.group(1)) if m else None


def resolve(platform: str, event: dict) -> tuple[list[str], str | None]:
    """回 (user_prompts, reply)。reply=None 代表讀不到（skip）、"" 代表真無輸出。"""
    if platform == "copilot":
        # copilot agentStop payload 用 camelCase sessionId（見 copilot adapter / fixtures）；
        # 兩種鍵都收，否則 sid 空 → read_copilot_history 找不到 → 回程靜默 no-op。
        sid = str(event.get("session_id") or event.get("sessionId") or "")
        data = read_copilot_history(Path.home(), sid)
        prompts = data.get("user_prompts", []) or []
        if not prompts and sid:
            _log("copilot", RuntimeError(f"history 無 prompts（session={sid}）→ no-op"))
        reply = data.get("assistant_summary", "") if prompts else None
        return prompts, reply
    # codex
    tp = event.get("transcript_path")
    prompts: list[str] = []
    if tp:
        try:
            prompts = read_codex_rollout(tp).get("user_prompts", []) or []
        except Exception as exc:
            _log("rollout", exc)
    reply = event["last_assistant_message"] if "last_assistant_message" in event else None
    if reply is not None and not isinstance(reply, str):
        reply = None
    return prompts, reply


def handle_resolved(*, prompts: list[str], reply: str | None, sender=_send_via_bridge) -> bool:
    user_id = _discover_user_id(prompts)
    if user_id is None:
        return False  # turn-scoped no-op（本地輸入 / 非 bro 路由 / manager headless）
    if reply is None:
        _log("reply", RuntimeError("本輪回覆讀不到 → skip（不送 EMPTY_NOTICE）"))
        return False
    try:
        sender(user_id, reply or EMPTY_NOTICE)
    except Exception as exc:
        _log("send", exc)
        return False
    return True


def handle(event: dict, platform: str, sender=_send_via_bridge) -> bool:
    try:
        prompts, reply = resolve(platform, event)
    except Exception as exc:
        _log("resolve", exc)
        return False
    return handle_resolved(prompts=prompts, reply=reply, sender=sender)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=["codex", "copilot"])
    args = parser.parse_args()
    try:
        handle(json.load(sys.stdin), args.platform)
    except Exception as exc:  # hook must never break the agent
        _log("main", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
