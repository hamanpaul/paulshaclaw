"""One-shot migration: re-key knowledge slices from a legacy raw-remote project
key to a registered short slug (#177).

Recall filters by strict project equality, and some call sites also derive the
knowledge directory from a sanitized project slug. A safe migration therefore
must rewrite frontmatter ``project`` AND move the file into ``knowledge/<slug>``;
doing only one would leave recall in a torn state. The migration writes an
audit manifest, supports dry-run/apply, rebuilds MOCs and the retrieval index
through ``run_moc``, and never touches ``retrieval.db`` directly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .atomizer.config import is_safe_path_component, sanitize_project_component
from .moc import frontmatter_io as _fio
from .moc.runner import run_moc


class RekeyError(ValueError):
    """Raised when the requested rekey operation is invalid."""


def _write_manifest(manifest: Path, rows: list[dict]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(manifest)


def rekey_project(
    memory_root: Path,
    *,
    old_key: str,
    new_slug: str,
    now: str,
    apply: bool,
) -> dict:
    """Re-key knowledge slices whose frontmatter project equals ``old_key``."""

    if not is_safe_path_component(new_slug):
        raise RekeyError(f"--to must be a path-safe slug (no '/'): {new_slug!r}")
    if not old_key.strip() or old_key == new_slug:
        raise RekeyError("--from must be a non-empty key different from --to")

    knowledge = memory_root / "knowledge"
    target_dir = knowledge / sanitize_project_component(new_slug)
    rows: list[dict] = []

    for path in sorted(knowledge.rglob("*.md")) if knowledge.exists() else []:
        if path.name.endswith("-moc.md"):
            continue
        try:
            frontmatter, _body = _fio.read(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if frontmatter.get("memory_layer") != "knowledge":
            continue
        if str(frontmatter.get("project", "")) != old_key:
            continue

        target = target_dir / path.name
        base = {
            "slice_id": str(frontmatter.get("slice_id", "")),
            "from": old_key,
            "to": new_slug,
            "path": str(path),
            "target": str(target),
        }
        if not apply:
            rows.append({**base, "status": "dry-run"})
            continue
        if target != path and target.exists():
            rows.append({**base, "status": "conflict"})
            continue

        _fio.update(path, {"project": new_slug})
        target_dir.mkdir(parents=True, exist_ok=True)
        if target != path:
            path.rename(target)
        rows.append({**base, "status": "rekeyed"})

    manifest = memory_root / "runtime" / "ledger" / f"rekey-{now.replace(':', '')}.jsonl"
    _write_manifest(manifest, rows)

    counts = Counter(row["status"] for row in rows)
    removed_source_dir = False
    removed_orphan_moc = False
    if apply and counts.get("rekeyed", 0):
        source_dir = knowledge / sanitize_project_component(old_key)
        if source_dir.is_dir() and not any(source_dir.iterdir()):
            source_dir.rmdir()
            removed_source_dir = True
        orphan_moc = knowledge / f"{sanitize_project_component(old_key)}-moc.md"
        if orphan_moc.exists():
            orphan_moc.unlink()
            removed_orphan_moc = True
        run_moc(memory_root, now)

    return {
        "candidates": len(rows),
        "applied": apply,
        "rekeyed": counts.get("rekeyed", 0),
        "planned": counts.get("dry-run", 0),
        "conflicts": counts.get("conflict", 0),
        "removed_source_dir": removed_source_dir,
        "removed_orphan_moc": removed_orphan_moc,
        "manifest": str(manifest),
    }
