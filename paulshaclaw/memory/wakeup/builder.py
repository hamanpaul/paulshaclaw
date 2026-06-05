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

    # guard empty or unknown project
    if project in ("_unknown", ""):
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

    # Build Recent block (one-line summaries) - summary must come from the slice body per spec
    recent_lines: List[str] = []
    for s in active_slices[:k]:
        body = (s.get("body") or "")
        # find first meaningful (non-empty) line from body
        summary = ""
        for line in body.splitlines():
            line = line.strip()
            if line:
                summary = line
                break
        if not summary:
            # fallback to title if body has no meaningful lines
            summary = s.get("title") or ""
        # recent line: keep slice id for backward compat, add title stem and ts per plan
        stem = s.get("title") or ""
        ts = s.get("last_event_ts") or ""
        recent_lines.append(f"- {s['slice_id']} [[{stem}]] — {summary} ({ts})")

    header = f"# Memory wake-up — {project}\n\n"
    map_header = "## Map\n\n"
    recent_header = "## Recent\n\n"

    recent_block = recent_header + "\n".join(recent_lines) + "\n\n"

    moc_body = (moc_body or "")

    def clamp(text: str, budget: int) -> str:
        # return a prefix of text that does not exceed budget characters
        if len(text) <= budget:
            return text
        return text[:budget]

    # Respect char budget: try to keep Map before Recent per spec, truncating only the Map tail.
    # We must ensure the result does not exceed char_budget; if necessary trim recent entries to allow a Map header
    remaining_after_header = max(0, char_budget - len(header))

    # work with a mutable copy of recent lines so we can trim if needed
    recent_lines_mut = list(recent_lines)

    while True:
        # rebuild recent block for current lines (do not rstrip — we account exactly for bytes)
        current_recent_block = recent_header + "\n".join(recent_lines_mut) + "\n\n"
        # minimal required for map (header only)
        needed_for_map_header_and_recent = len(map_header) + len(current_recent_block)
        if needed_for_map_header_and_recent > remaining_after_header:
            # not enough room: trim the last recent line and retry (prefer Map header per spec)
            if recent_lines_mut:
                recent_lines_mut.pop()
                continue
            else:
                # no recent lines left; try to include minimal map marker first
                minimal_map_section = map_header + "\n\n(truncated)\n"
                if len(minimal_map_section) <= remaining_after_header:
                    return clamp(header + minimal_map_section, char_budget)
                # if minimal map doesn't fit, prefer keeping Recent header for continuity if possible
                if len(recent_header) <= remaining_after_header:
                    return clamp(header + recent_header, char_budget)
                # as an extreme fallback, return a clamped header (do not append newlines that could re-grow)
                return clamp(header, char_budget)
        else:
            # we have room for map header and current recent block; allocate remaining to map body
            allowed_body = remaining_after_header - len(current_recent_block) - len(map_header)
            if allowed_body <= 0:
                # include map header and truncated marker
                map_block = map_header + "\n\n(truncated)\n"
            else:
                if len(moc_body) > allowed_body:
                    marker = "\n\n(truncated)\n"
                    # reserve room for marker within allowed_body
                    slice_len = max(0, allowed_body - len(marker))
                    truncated_body = moc_body[:slice_len] + marker
                else:
                    truncated_body = moc_body
                map_block = map_header + truncated_body
            result = header + map_block + current_recent_block
            # defensive: ensure we never exceed char_budget
            if len(result) > char_budget:
                # try to shrink recent block further if possible
                if recent_lines_mut:
                    recent_lines_mut.pop()
                    continue
                # as last resort, truncate the result to budget
                return clamp(result, char_budget)
            return result
