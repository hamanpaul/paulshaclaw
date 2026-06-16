"""GitHub Copilot CLI sessionEnd payload adapter."""

from __future__ import annotations

from pathlib import Path

from .base import (
    AdapterResult,
    build_session,
    read_copilot_history,
    read_payload,
    string_or_empty,
    string_or_none,
)


def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    session_id = string_or_empty(payload.get("sessionId")) or string_or_empty(payload.get("session_id"))
    config_root = (
        payload.get("psc_config_root")
        or payload.get("PSC_CONFIG_ROOT")
        or str(Path.home())
    )
    if session_id:
        content = read_copilot_history(config_root, session_id)
        if content.get("user_prompts") or content.get("assistant_summary"):
            payload = {**payload, **content}
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="copilot-cli",
        session_id=session_id,
        default_capture_scope="session_end",
        ended_at=string_or_none(payload.get("timestamp")) or string_or_none(payload.get("ended_at")),
    )
