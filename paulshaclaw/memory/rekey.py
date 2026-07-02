"""One-shot migration: re-key knowledge slices from a legacy raw-remote project
key to a registered short slug (#177).

Recall filters by strict project equality, and some call sites also derive the
per-project directory from a sanitized project slug. A safe migration therefore
must rewrite frontmatter ``project`` AND move the file into the sanitized slug directory;
doing only one would leave recall in a torn state. The migration writes an
audit manifest, supports dry-run/apply, rebuilds MOCs and the retrieval index
through ``run_moc``, and never touches ``retrieval.db`` directly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .atomizer.config import is_safe_path_component, sanitize_project_component
from .moc import frontmatter_io as _fio
from .moc import naming as _moc_naming
from .moc import runner as _moc_runner
from .moc.runner import run_moc


class RekeyError(ValueError):
    """Raised when the requested rekey operation is invalid."""


def _write_manifest(manifest: Path, rows: list[dict]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(manifest)


def _reconcile_preserving_paths(memory_root: Path, protected_paths: set[Path]) -> list[str]:
    knowledge = memory_root / "knowledge"
    warnings: list[str] = []
    if not knowledge.exists():
        return warnings

    protected_existing = tuple(path for path in protected_paths if path.exists())
    protected_resolved = {path.resolve() for path in protected_existing}
    protected_slice_ids: set[str] = set()
    for path in protected_existing:
        frontmatter, _body = _fio.read(path.read_text(encoding="utf-8"))
        if frontmatter.get("memory_layer") != "knowledge":
            continue
        slice_id = str(frontmatter.get("slice_id", ""))
        if slice_id:
            protected_slice_ids.add(slice_id)

    seen: dict[str, Path] = {}
    for path in sorted(knowledge.rglob("*.md")):
        frontmatter, body = _fio.read(path.read_text(encoding="utf-8"))
        if frontmatter.get("memory_layer") != "knowledge":
            continue
        slice_id = frontmatter.get("slice_id")
        if not slice_id:
            warnings.append(f"{path}: missing slice_id; skipped")
            continue
        if path.resolve() in protected_resolved:
            seen.setdefault(str(slice_id), path)
            continue
        target = path.with_name(_moc_naming.target_name(frontmatter, body))
        if path != target:
            if target.exists():
                if target.resolve() in protected_resolved:
                    seen.setdefault(str(slice_id), path)
                    continue
                if path.stat().st_mtime <= target.stat().st_mtime:
                    path.unlink()
                    continue
                target.unlink()
            path.rename(target)
            path = target
        slice_id_str = str(slice_id)
        if slice_id_str in protected_slice_ids:
            seen.setdefault(slice_id_str, path)
            continue
        if slice_id_str in seen:
            other = seen[slice_id_str]
            if path.resolve() != other.resolve():
                older = other if other.stat().st_mtime <= path.stat().st_mtime else path
                newer = path if older is other else other
                older.unlink()
                seen[slice_id_str] = newer
                warnings.append(f"duplicate slice_id {slice_id}; kept {newer.name}")
        else:
            seen[slice_id_str] = path
    return warnings


def _run_moc_preserving_conflicts(memory_root: Path, now: str, protected_paths: set[Path]) -> dict:
    if not protected_paths:
        return run_moc(memory_root, now)
    original_reconcile = _moc_runner.naming.reconcile
    original_build_index = _moc_runner.search.build_index
    _moc_runner.naming.reconcile = lambda root: _reconcile_preserving_paths(root, protected_paths)
    _moc_runner.search.build_index = (
        lambda root, link_weights, *, doc_corpus=None: _build_index_excluding_paths(
            root,
            link_weights,
            doc_corpus=doc_corpus,
            protected_paths=protected_paths,
            build_index=original_build_index,
        )
    )
    try:
        return run_moc(memory_root, now)
    finally:
        _moc_runner.naming.reconcile = original_reconcile
        _moc_runner.search.build_index = original_build_index


def _build_index_excluding_paths(
    memory_root: Path,
    link_weights: dict[str, int],
    *,
    doc_corpus: object | None,
    protected_paths: set[Path],
    build_index,
) -> None:
    existing = tuple(path for path in sorted(protected_paths) if path.exists())
    if not existing:
        build_index(memory_root, link_weights, doc_corpus=doc_corpus)
        return
    runtime = memory_root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=runtime, prefix="rekey-conflicts-") as tmpdir:
        stash_root = Path(tmpdir)
        moved: list[tuple[Path, Path]] = []
        for index, path in enumerate(existing):
            parked = stash_root / f"{index}-{path.name}"
            path.rename(parked)
            moved.append((path, parked))
        try:
            build_index(memory_root, link_weights, doc_corpus=doc_corpus)
        finally:
            for original, parked in reversed(moved):
                if parked.exists():
                    original.parent.mkdir(parents=True, exist_ok=True)
                    parked.rename(original)


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
    planned: list[tuple[Path, Path, dict]] = []

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
        row = {**base, "status": "planned"}
        rows.append(row)
        planned.append((path, target, row))

    manifest = memory_root / "runtime" / "ledger" / f"rekey-{now.replace(':', '')}.jsonl"
    _write_manifest(manifest, rows)

    for path, target, row in planned:
        moved = False
        active_path = path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target != path:
                path.rename(target)
                moved = True
                active_path = target
            _fio.update(active_path, {"project": new_slug})
            row["status"] = "rekeyed"
        except OSError as exc:
            if moved and active_path.exists() and not path.exists():
                try:
                    active_path.rename(path)
                except OSError as rollback_exc:
                    row["rollback_error"] = str(rollback_exc)
            row["status"] = "error"
            row["error"] = str(exc)

    if apply:
        _write_manifest(manifest, rows)

    counts = Counter(row["status"] for row in rows)
    removed_source_dir = False
    removed_orphan_moc = False
    indexed = None
    warnings: list[str] = []
    if apply and counts.get("rekeyed", 0):
        source_dir = knowledge / sanitize_project_component(old_key)
        if source_dir.is_dir() and not any(source_dir.iterdir()):
            source_dir.rmdir()
            removed_source_dir = True
        orphan_moc = knowledge / f"{sanitize_project_component(old_key)}-moc.md"
        if orphan_moc.exists():
            orphan_moc.unlink()
            removed_orphan_moc = True
        conflict_paths = {Path(row["path"]) for row in rows if row["status"] == "conflict"}
        moc_result = _run_moc_preserving_conflicts(memory_root, now, conflict_paths)
        indexed = moc_result.get("indexed")
        warnings = list(moc_result.get("warnings", []))

    return {
        "candidates": len(rows),
        "applied": apply,
        "rekeyed": counts.get("rekeyed", 0),
        "planned": counts.get("dry-run", 0),
        "conflicts": counts.get("conflict", 0),
        "errors": counts.get("error", 0),
        "removed_source_dir": removed_source_dir,
        "removed_orphan_moc": removed_orphan_moc,
        "indexed": indexed,
        "warnings": warnings,
        "manifest": str(manifest),
    }
