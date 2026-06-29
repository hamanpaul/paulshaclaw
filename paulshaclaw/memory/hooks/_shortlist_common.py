"""Prompt-time shortlist: bm25 search -> shortlist injection + offered recording. Best-effort IO."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from paulshaclaw.memory.importer.project_resolver import resolve_project
from paulshaclaw.memory.moc import search as search_mod
from paulshaclaw.memory.retrieval import format_shortlist, to_fts_query
from paulshaclaw.memory.hooks._wakeup_common import log_warn, sanitize_id

SHORTLIST_K = 3


def _summary(path: str) -> str:
    """First meaningful (non-frontmatter, non-empty) body line, for the shortlist."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = text.splitlines()
    # skip YAML frontmatter if present
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        lines = lines[end + 1:]
    for ln in lines:
        s = ln.strip()
        if s:
            return s.lstrip("# ").strip()
    return ""


def _record_offered(root: Path, tool: str, session_id: str, project: str,
                    offered: list[tuple[str, str]]) -> None:
    """Append offered ledger + accumulate per-session sl_id<->path map. Best-effort."""
    try:
        led_dir = root / "runtime" / "ledger"
        led_dir.mkdir(parents=True, exist_ok=True)
        ev = {"ts": datetime.now(timezone.utc).isoformat(), "session_id": session_id,
              "tool": tool, "project": project,
              "offered": [{"sl_id": sid, "path": p} for sid, p in offered]}
        with (led_dir / "offered.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

        wk_dir = root / "runtime" / "wakeup"
        wk_dir.mkdir(parents=True, exist_ok=True)
        mpath = wk_dir / f"{tool}__{sanitize_id(session_id)}.offered.json"
        cur = {"by_path": {}, "by_id": {}}
        if mpath.exists():
            try:
                cur = json.loads(mpath.read_text(encoding="utf-8"))
            except Exception:
                cur = {"by_path": {}, "by_id": {}}
        for sid, p in offered:
            cur["by_path"][p] = sid
            cur["by_id"][sid] = p
        tmp = mpath.with_name(f".{mpath.name}.tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        tmp.replace(mpath)
    except Exception as exc:
        log_warn(root, tool, f"failed to record offered: {exc}")


def build_shortlist_and_record(root: Path, tool: str, session_id: str,
                               cwd: str | None, prompt: str) -> str:
    """Resolve project, search by prompt, build shortlist, record offered. Returns '' if nothing."""
    try:
        if not prompt or prompt.lstrip().startswith("/"):
            return ""
        project = resolve_project(cwd=cwd, memory_root=str(root))
        if project in ("_unknown", ""):
            return ""
        query = to_fts_query(prompt)
        if not query:
            return ""
        try:
            hits = search_mod.search(root, query, project=project,
                                     limit=SHORTLIST_K, include_decayed=False)
        except search_mod.SearchIndexError:
            return ""
        if not hits:
            return ""
        for h in hits:
            h["summary"] = _summary(h.get("path", ""))
        block = format_shortlist(hits)
        offered = [(h["slice_id"], h["path"]) for h in hits if h.get("path")]
        _record_offered(root, tool, session_id, project, offered)
        return block
    except Exception as exc:
        log_warn(root, tool, f"shortlist failed: {exc}")
        return ""
