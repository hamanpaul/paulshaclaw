from __future__ import annotations

from pathlib import Path
from typing import List

from ..ledger import lifecycle
from ..ledger import retrieval_set
from ..moc import frontmatter_io as fio


def build_brief(memory_root: Path, project: str, *, now: str, k: int = 8, char_budget: int = 8000) -> str:
    """Build a deterministic, read-only wake-up brief for a project.

    See task description for behavior. This implementation is conservative and
    fail-open: unreadable files are skipped.
    """
    memory_root = Path(memory_root)

    if project == "_unknown":
        return ""

    # Read MOC
    moc_path = memory_root / "knowledge" / f"{project}-moc.md"
    moc_body = None
    if moc_path.exists():
        try:
            _, body = fio.read(moc_path.read_text(encoding="utf-8"))
            moc_body = body
        except Exception:
            moc_body = None

    # Discover candidate slice files under knowledge/<project>
    kdir = memory_root / "knowledge" / project
    slices: List[dict] = []
    if kdir.exists():
        for path in sorted(kdir.rglob("*.md")):
            try:
                fm, body = fio.read(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if fm.get("memory_layer") != "knowledge":
                continue
            if str(fm.get("project")) != project:
                continue
            sid = fm.get("slice_id")
            if not sid:
                continue
            title = fm.get("title") or path.stem.rsplit("--", 1)[0]
            slices.append({"slice_id": str(sid), "title": title, "body": body})

    if moc_body is None or not slices:
        # Per spec: empty string when no relevant MOC/slices
        return ""

    # Compute active slices and lifecycle state
    events = lifecycle.read_events(memory_root)
    lifecycle_state = lifecycle.fold_lifecycle(events)

    # Determine active slice ids respecting no-events semantics
    candidate_ids = [s["slice_id"] for s in slices]
    active_ids = retrieval_set.active_records(memory_root, candidate_ids)

    # Filter slices to only active ones
    active_slices = [s for s in slices if s["slice_id"] in active_ids]
    if not active_slices:
        return ""

    # Attach last_event_ts for sorting
    for s in active_slices:
        sid = s["slice_id"]
        rec = lifecycle_state.get(sid, {})
        s["last_event_ts"] = rec.get("last_event_ts")

    # Sort by recency descending, tie-break by slice_id
    active_slices.sort(key=lambda x: ((x.get("last_event_ts") or ""), x["slice_id"]))
    active_slices = list(reversed(active_slices))

    # Build Recent block (one-line summaries)
    recent_lines: List[str] = []
    for s in active_slices[:k]:
        summary = ""
        # Use title if present, else first line of body
        if s.get("title"):
            summary = s["title"]
        else:
            summary = (s.get("body") or "").splitlines()[0] if (s.get("body") or "") else ""
        recent_lines.append(f"- {s['slice_id']}: {summary}")

    header = f"# Memory wake-up — {project}\n\n"
    map_header = "## Map\n\n"
    recent_header = "## Recent\n\n"

    recent_block = recent_header + "\n".join(recent_lines) + "\n\n"

    map_block = map_header + (moc_body or "")

    # Respect char budget: preserve header + recent first, truncate map tail if necessary
    full_without_trunc = header + map_block + recent_block
    if len(full_without_trunc) <= char_budget:
        # Place Map before Recent per spec
        return header + map_block + recent_block

    # Otherwise, ensure header+recent preserved and truncate map
    preserved = header + recent_block
    allowed_for_map = max(0, char_budget - len(preserved))
    if allowed_for_map <= 0:
        # No room for map; return header + recent only
        return preserved.rstrip() + "\n"

    # Truncate map body to allowed_for_map length
    # Ensure we include the map header in the budget
    map_body_only = (moc_body or "")
    # If allowed includes map_header length, subtract it when slicing body
    map_header_len = len(map_header)
    if allowed_for_map <= map_header_len:
        # Not enough room even for map header text; omit map and mark truncated
        return preserved.rstrip() + "\n"
    allowed_body = allowed_for_map - map_header_len
    if len(map_body_only) > allowed_body:
        truncated_body = map_body_only[:allowed_body].rstrip() + "\n\n(truncated)\n"
    else:
        truncated_body = map_body_only
    map_block = map_header + truncated_body
    return header + map_block + recent_block
