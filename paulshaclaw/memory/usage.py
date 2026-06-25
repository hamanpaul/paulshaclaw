"""Memory consumption telemetry helpers (#148). Pure functions, no IO."""

from __future__ import annotations

import re

# Prepended to a non-empty wake-up brief so agents can mark which memories they used.
CITATION_PREAMBLE = (
    "> 記憶使用追蹤：若你在本次工作中參考了下列任一條記憶，請在回覆中標註其 "
    "`[[sl-xxxxxxxxxxxxxxxx]]`（16-hex id），以便評估記憶實際效用。\n\n"
)

_SLICE_ID = re.compile(r"sl-[0-9a-f]{16}")
_WIKILINK = re.compile(r"\[\[([^\]|]+)\|([^\]]*)\]\]")
_MATCH_MIN_TITLE = 8


def extract_offered(brief: str) -> list[tuple[str, str]]:
    """Extract (slice_id, title) pairs from a brief's [[stem--sl-id|title]] wikilinks."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for target, title in _WIKILINK.findall(brief):
        m = _SLICE_ID.search(target)
        if not m or m.group(0) in seen:
            continue
        seen.add(m.group(0))
        out.append((m.group(0), title.strip()))
    return out


def extract_cited(assistant_text: str, offered_ids) -> set[str]:
    """Slice ids the agent explicitly referenced (in [[..]] or bare) that were offered."""
    offered = set(offered_ids)
    return {sid for sid in _SLICE_ID.findall(assistant_text or "") if sid in offered}


def extract_matched(assistant_text: str, offered, *, exclude=()) -> set[str]:
    """Offered ids whose (>=8 char) title appears verbatim in assistant text, minus exclude."""
    text = assistant_text or ""
    skip = set(exclude)
    out: set[str] = set()
    for sid, title in offered:
        t = (title or "").strip()
        if sid in skip or len(t) < _MATCH_MIN_TITLE:
            continue
        if t in text:
            out.add(sid)
    return out
