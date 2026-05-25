"""Codex Stop/SubagentStop payload adapter."""

from __future__ import annotations

from pathlib import Path

from .base import AdapterResult, build_session, read_payload, string_or_empty


def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="codex",
        session_id=string_or_empty(payload.get("session_id")),
        default_capture_scope="turn",
        ended_at=None,
    )
