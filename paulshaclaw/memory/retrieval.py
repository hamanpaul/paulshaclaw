# paulshaclaw/memory/retrieval.py
"""Pure retrieval helpers (no IO): FTS query sanitization + shortlist formatting."""
from __future__ import annotations

import re

# alnum/underscore runs, or contiguous CJK runs
_TOKEN = re.compile(r"[0-9A-Za-z_]+|[一-鿿]+")

_SHORTLIST_HINT = "> 與當前任務相關的記憶（相關項用 Read 開啟下列絕對路徑取全文）："


def to_fts_query(prompt: str) -> str:
    """Build a safe FTS5 MATCH query from arbitrary prompt text.

    Extracts alnum/CJK tokens, drops 1-char latin tokens, quotes each token as
    an FTS5 string literal (neutralizing operators), and OR-joins them. Empty or
    token-less input returns "" (caller treats as 'do not search').
    """
    if not prompt:
        return ""
    toks = [t for t in _TOKEN.findall(prompt) if (len(t) >= 2 or not t.isascii())]
    if not toks:
        return ""
    return " OR ".join(f'"{t}"' for t in toks)


def format_shortlist(hits: list[dict]) -> str:
    """Render hits ({title, summary, path}) as an injected shortlist block. [] -> ''."""
    if not hits:
        return ""
    lines = [_SHORTLIST_HINT]
    for h in hits:
        title = (h.get("title") or "").strip() or "(untitled)"
        summary = (h.get("summary") or "").strip()
        path = h.get("path") or ""
        lines.append(f"- [{title}] — {summary} — {path}")
    return "\n".join(lines)
