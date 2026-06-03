from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from paulshaclaw.memory.moc import frontmatter_io


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Convert title to kebab-case slug."""
    slug = _SLUG_STRIP.sub("-", title.strip().lower()).strip("-")
    return slug or "untitled"


def _title(fm: dict[str, Any], body: str) -> str:
    """Extract title from frontmatter, markdown heading, or fallback."""
    title = fm.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading
    return f"{fm.get('artifact_kind', 'note')}-{fm.get('project', 'unknown')}"


def target_name(fm: dict[str, Any], body: str) -> str:
    """Generate target filename: <slug>--<slice_id>.md"""
    return f"{slugify(_title(fm, body))}--{fm['slice_id']}.md"


def reconcile(memory_root: Path) -> list[str]:
    """Rename slices to <title>--<slice_id>.md and dedup by slice_id. Returns warnings."""
    knowledge = memory_root / "knowledge"
    warnings: list[str] = []
    if not knowledge.exists():
        return warnings
    seen: dict[str, Path] = {}
    for path in sorted(knowledge.rglob("*.md")):
        fm, body = frontmatter_io.read(path.read_text(encoding="utf-8"))
        if fm.get("memory_layer") != "knowledge":
            continue
        slice_id = fm.get("slice_id")
        if not slice_id:
            warnings.append(f"{path}: missing slice_id; skipped")
            continue
        target = path.with_name(target_name(fm, body))
        if path != target:
            if target.exists():
                # Only overwrite if current file is newer
                if path.stat().st_mtime <= target.stat().st_mtime:
                    path.unlink()
                    continue
                target.unlink()
            path.rename(target)
            path = target
        if slice_id in seen:
            other = seen[slice_id]
            if path.resolve() != other.resolve():
                older = other if other.stat().st_mtime <= path.stat().st_mtime else path
                newer = path if older is other else other
                older.unlink()
                seen[slice_id] = newer
                warnings.append(f"duplicate slice_id {slice_id}; kept {newer.name}")
        else:
            seen[slice_id] = path
    return warnings
