# paulshaclaw/memory/moc/moc_builder.py
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..atomizer.config import sanitize_project_component
from ..ledger import retrieval_set
from . import frontmatter_io as fio


def _active_slices(memory_root: Path) -> list[tuple[str, str, str, str]]:
    """Return (slice_id, project, basename, artifact_kind) for active knowledge slices."""
    knowledge = memory_root / "knowledge"
    rows: list[tuple[str, str, str, str]] = []
    if not knowledge.exists():
        return rows
    candidates: list[tuple[str, str, str, str]] = []
    for path in sorted(knowledge.rglob("*.md")):
        fm, _ = fio.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        sid = fm.get("slice_id")
        if not sid:
            continue
        candidates.append((str(sid), str(fm.get("project", "_unknown")), path.stem,
                           str(fm.get("artifact_kind", "")),
                           str(fm.get("source_session", "")), str(fm.get("session_title", ""))))
    active = set(retrieval_set.active_records(memory_root, [c[0] for c in candidates]))
    return [c for c in candidates if c[0] in active]


def _write_moc(path: Path, kind: str, now: str, header: str, lines: list[str], project: str | None = None) -> None:
    fm = ["---", "memory_layer: moc", f"moc_kind: {kind}", f"generated_ts: {now}"]
    if project is not None:
        fm.append(f"project: {project}")
    fm.append("---")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(fm) + f"\n# {header}\n\n" + "\n".join(lines) + "\n", encoding="utf-8")


def build_mocs(memory_root: Path, now: str) -> None:
    knowledge = memory_root / "knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    rows = _active_slices(memory_root)
    by_project: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
    for row in rows:
        by_project[row[1]].append(row)

    for project, items in by_project.items():
        if project == "common-sense":
            continue
        lines = [f"- [[{basename}{('|' + st) if st else ''}]] — {kind}" for _, _, basename, kind, _, st in sorted(items)]
        _write_moc(knowledge / f"{sanitize_project_component(project)}-moc.md", "project", now, f"{project} MOC", lines, project)

    cs = [f"- [[{b}{('|' + st) if st else ''}]] — {k}" for sid, p, b, k, _, st in sorted(rows) if p == "common-sense"]
    _write_moc(knowledge / "common-sense-moc.md", "common-sense", now, "Common-sense MOC", cs)

    active_lines = ["## Active", ""] + [f"- [[{b}{('|' + st) if st else ''}]] — {p} · {k}" for sid, p, b, k, _, st in sorted(rows)]
    _write_moc(knowledge / "wiki-moc.md", "wiki", now, "Wiki MOC", active_lines)
