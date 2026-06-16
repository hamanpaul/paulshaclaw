"""Per-session <=20-char zh-TW title generation via local gemma4, with offline fallback.

The title is generated at import time and stored as the session's ``assistant_summary``
(rendered under ## Summary) plus a ``title_source`` marker (gemma4 | fallback). Title
generation never blocks or fails the import: if the LLM backend is unavailable the title
falls back to the first user prompt truncated, marked ``fallback`` for later regeneration.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from pathlib import Path
from typing import Any, Callable

_MAX = 20
_DEFAULT_COMMAND: tuple[str, ...] = ("scripts/claude-gemma4",)
_PROMPT = (
    "請用繁體中文為以下工作 session 下一個標題，最多 20 個字、單行、不要標點或引號：\n\n"
    "使用者需求：{prompt}\n\n助理結論：{summary}\n\n標題："
)


def _truncate(text: str, limit: int = _MAX) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())[:limit]


def _gemma4_reachable(timeout: float = 0.3) -> bool:
    """Fast TCP pre-check so an offline backend fails over to the fallback title
    instantly, instead of blocking the import on a long subprocess timeout."""
    host = os.environ.get("PSC_GEMMA4_HOST", "127.0.0.1")
    port = int(os.environ.get("PSC_GEMMA4_PORT", "8001"))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _default_runner(text: str, command: tuple[str, ...], timeout: int) -> str:
    if not _gemma4_reachable():
        raise RuntimeError("gemma4 backend not reachable")
    proc = subprocess.run(
        list(command), input=text, capture_output=True, text=True, timeout=timeout
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gemma4 exit {proc.returncode}: {proc.stderr[:200]}")
    return proc.stdout


def generate_title(
    session: dict[str, Any],
    *,
    command: tuple[str, ...] = _DEFAULT_COMMAND,
    timeout: int = 60,
    runner: Callable[[str, tuple[str, ...], int], str] | None = None,
) -> tuple[str, str]:
    """Return (title, source). source is 'gemma4' on success, 'fallback' otherwise."""
    prompts = session.get("user_prompts") or []
    first_prompt = prompts[0] if prompts else ""
    runner = runner or _default_runner
    text = _PROMPT.format(
        prompt=first_prompt[:500],
        summary=(session.get("assistant_summary") or "")[:500],
    )
    try:
        title = _truncate(runner(text, command, timeout))
        if title:
            return title, "gemma4"
    except Exception:
        pass
    return _truncate(first_prompt), "fallback"


def _cache_path(memory_root: str | Path, session_id: str) -> Path:
    safe = re.sub(r"[\\/]+", "__", (session_id or "_unknown"))
    return Path(memory_root) / "runtime" / "cache" / "title" / f"{safe}.json"


def apply(session: dict[str, Any], *, memory_root: str | Path, **kwargs: Any) -> dict[str, Any]:
    """Generate (or reuse cached) title and set session['assistant_summary'] + 'title_source'."""
    cache = _cache_path(memory_root, session.get("session_id") or "")
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            session["assistant_summary"] = cached["title"]
            session["title_source"] = cached["source"]
            return session
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    title, source = generate_title(session, **kwargs)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_name(f".{cache.name}.tmp")
    tmp.write_text(json.dumps({"title": title, "source": source}), encoding="utf-8")
    tmp.replace(cache)
    session["assistant_summary"] = title
    session["title_source"] = source
    return session
