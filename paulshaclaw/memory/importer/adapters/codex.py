"""Codex Stop/SubagentStop payload adapter."""

from __future__ import annotations

from pathlib import Path

from .base import (
    AdapterResult,
    build_session,
    read_codex_rollout,
    read_payload,
    string_or_empty,
    string_or_none,
)


def extract(queue_path: str | Path) -> AdapterResult:
    payload = read_payload(queue_path)
    enrich: dict = {}
    last = payload.get("last_assistant_message")
    if isinstance(last, str) and last.strip():
        enrich["assistant_summary"] = last
    transcript_path = payload.get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        enrich.update(read_codex_rollout(transcript_path))
    if enrich:
        payload = {**payload, **enrich}
    return build_session(
        payload=payload,
        queue_path=queue_path,
        tool="codex",
        session_id=string_or_empty(payload.get("session_id")),
        default_capture_scope="turn",
        ended_at=string_or_none(payload.get("ended_at")),
    )
