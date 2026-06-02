from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..ledger import lifecycle, processing, relations


class BundleError(Exception):
    pass


def _frontmatter_lines(text: str) -> list[str]:
    lines = (text or "").splitlines()
    if not lines or lines[0] != "---":
        return []
    try:
        end = lines.index("---", 1)
    except ValueError:
        return []
    return lines[1:end]


def _frontmatter_value(lines: Iterable[str], key: str) -> str | None:
    prefix = f"{key}:"
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip() or None
    return None


def _slice_id_of(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    fm = _frontmatter_lines(text)
    return _frontmatter_value(fm, "slice_id") or path.stem


def _distilled_from(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    fm = _frontmatter_lines(text)
    return _frontmatter_value(fm, "distilled_from")


def _canonical_jsonl_line(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"))


def build(
    memory_root: Path,
    slice_paths: Sequence[Path],
    out_dir: Path,
    *,
    selection: dict[str, object],
    now: str,
) -> Path:
    slice_infos: list[tuple[str, Path, str | None]] = []
    seen: dict[str, Path] = {}
    sessions: set[str] = set()

    for src in slice_paths:
        sid = _slice_id_of(src)
        if sid in seen:
            raise BundleError(f"duplicate slice_id '{sid}' selected in {seen[sid]!s} and {src!s}")
        seen[sid] = src
        session = _distilled_from(src)
        slice_infos.append((sid, src, session))
        if session:
            sessions.add(session)

    out_dir.mkdir(parents=True, exist_ok=True)
    slices_out = out_dir / "slices"
    slices_out.mkdir(parents=True, exist_ok=True)

    slice_ids = [sid for sid, _, _ in slice_infos]
    for sid, src, _session in slice_infos:
        shutil.copyfile(src, slices_out / f"{sid}.md")

    unique_slice_ids = sorted(set(slice_ids))
    slice_id_set = set(unique_slice_ids)
    node_set = {f"slice:{sid}" for sid in unique_slice_ids} | {f"session:{s}" for s in sessions}

    events: list[dict[str, Any]] = []

    try:
        lifecycle_events = lifecycle.read_events(memory_root)
    except (OSError, UnicodeDecodeError, ValueError):
        lifecycle_events = []

    for event in lifecycle_events:
        if str(event.get("record_id", "")) in slice_id_set:
            events.append({"ledger": "lifecycle", **event})

    for edge in relations.read_edges(memory_root):
        if edge.get("from") in node_set or edge.get("to") in node_set:
            events.append({"ledger": "relations", **edge})

    for record in processing.read_events(memory_root):
        if record.get("session_key") in sessions:
            events.append({"ledger": "processing", **record})

    ledger_path = out_dir / "ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(_canonical_jsonl_line(event) + "\n")

    manifest = {
        "generated_ts": now,
        "selection": selection,
        "slice_ids": unique_slice_ids,
        "counts": {"slices": len(unique_slice_ids), "ledger_events": len(events)},
        "raw_excluded": True,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_dir
