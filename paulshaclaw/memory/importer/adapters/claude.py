"""Claude Code SessionEnd payload adapter."""

from __future__ import annotations

from pathlib import Path

from .base import (
    AdapterResult,
    build_session,
    read_claude_transcript,
    read_payload,
    string_or_empty,
    string_or_none,
)


def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    transcript_path = payload.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        payload = {**payload, **read_claude_transcript(transcript_path)}
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="claude-code",
        session_id=string_or_empty(payload.get("session_id")),
        default_capture_scope="session_end",
        ended_at=string_or_none(payload.get("ended_at")) or string_or_none(payload.get("timestamp")),
    )
