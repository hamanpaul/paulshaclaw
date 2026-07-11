"""Land Claude Code's live rate limits into the footer's trusted sidecar.

Claude Code passes `.rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}`
to its statusLine command on every refresh. The Stage 8 footer's `collect_claude`
reads that quota from a sidecar JSON (default
``~/.agents/state/cost/claude_rate_limits.json``) but nothing ever wrote it, so
`cc` stayed `--`. This module is that missing writer: mounted on the Claude Code
statusLine command, it captures the same `rate_limits` the statusline already
renders and lands it in the sidecar for the footer to read.

It must never break the statusline, so :func:`main` swallows every error and
always exits 0.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from paulshaclaw.cost.config import default_claude_statusline_sidecar

# Only the two windows the footer renders; extra statusline fields (model,
# context_window, effort, …) are ignored.
_FOOTER_WINDOWS = ("five_hour", "seven_day")


def extract_rate_limits(payload: Any) -> dict[str, dict[str, Any]] | None:
    """Pull the footer's two rate-limit windows out of a statusLine payload.

    Keeps only ``five_hour`` / ``seven_day`` and only when at least one carries a
    usable percentage. A payload without rate limits (or without any percentage)
    returns ``None`` so the caller never blanks a previously-good sidecar."""
    if not isinstance(payload, Mapping):
        return None
    raw = payload.get("rate_limits")
    if not isinstance(raw, Mapping):
        return None

    windows: dict[str, dict[str, Any]] = {}
    for key in _FOOTER_WINDOWS:
        window = raw.get(key)
        if not isinstance(window, Mapping):
            continue
        percent = window.get("used_percentage", window.get("used_percent"))
        if percent is None:
            continue
        entry: dict[str, Any] = {"used_percentage": percent}
        reset = window.get("resets_at", window.get("reset_at"))
        if reset is not None:
            # Kept verbatim (statusLine uses ISO8601); the footer parser accepts
            # both ISO8601 and epoch, so no conversion is needed here.
            entry["resets_at"] = reset
        windows[key] = entry

    return windows or None


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".claude_rate_limits.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def update_sidecar_from_statusline(
    raw_stdin: str, *, sidecar: Path | None = None
) -> bool:
    """Parse a statusLine payload and land its rate limits into the sidecar.

    Returns ``True`` when a fresh sidecar was written, ``False`` when the payload
    was malformed or carried no usable rate limits (existing sidecar untouched)."""
    try:
        payload = json.loads(raw_stdin)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    rate_limits = extract_rate_limits(payload)
    if rate_limits is None:
        return False
    target = Path(sidecar) if sidecar is not None else default_claude_statusline_sidecar()
    _atomic_write_json(target, {"rate_limits": rate_limits})
    return True


def main(argv: list[str] | None = None) -> int:
    # Mounted on the Claude Code statusLine command — it must never fail in a way
    # that breaks the statusline, so every error is swallowed and exit is always 0.
    try:
        raw = sys.stdin.read()
        update_sidecar_from_statusline(raw)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
