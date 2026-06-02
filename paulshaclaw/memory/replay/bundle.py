from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..ledger import lifecycle, processing, relations


class BundleError(Exception):
    pass


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _frontmatter_lines(text: str) -> list[str]:
    lines = (text or "").splitlines()
    if not lines or lines[0] != "---":
        return []
    try:
        end = lines.index("---", 1)
    except ValueError:
        return []
    return lines[1:end]


def _frontmatter_dict(text: str) -> dict[str, Any]:
    lines = _frontmatter_lines(text)
    if not lines:
        return {}
    block = "\n".join(lines)
    if not block.strip():
        return {}

    try:
        import yaml  # type: ignore

        data = yaml.safe_load(block)
        if isinstance(data, dict):
            return data
        return {}
    except Exception:
        return {}


def _frontmatter_value(lines: Iterable[str], key: str) -> str | None:
    prefix = f"{key}:"
    for line in lines:
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip() or None
    return None


def _frontmatter_yaml_or_raise(text: str, *, src: Path) -> dict[str, Any]:
    lines = _frontmatter_lines(text)
    if not lines:
        raise BundleError(f"slice missing YAML frontmatter: {src}")

    block = "\n".join(lines)
    if not block.strip():
        raise BundleError(f"slice YAML frontmatter is empty: {src}")

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise BundleError("PyYAML is required to validate slice frontmatter") from exc

    try:
        data = yaml.safe_load(block)
    except Exception as exc:
        raise BundleError(f"slice frontmatter is not valid YAML: {src}: {exc}") from exc

    if not isinstance(data, dict):
        raise BundleError(f"slice frontmatter must be a mapping: {src}")

    return data


def _validated_slice_info(knowledge_root: Path, src: Path) -> tuple[str, Path, str | None]:
    try:
        src_resolved = src.resolve(strict=True)
    except FileNotFoundError as exc:
        raise BundleError(f"slice path not found: {src}") from exc

    knowledge_root_resolved = knowledge_root.resolve(strict=False)
    if not _is_within(src_resolved, knowledge_root_resolved):
        raise BundleError(f"slice path must be under knowledge root: {src}")

    if not src_resolved.is_file():
        raise BundleError(f"slice path is not a file: {src}")

    try:
        text = src_resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise BundleError(f"slice unreadable: {src}: {exc}") from exc

    fm = _frontmatter_yaml_or_raise(text, src=src_resolved)

    if fm.get("memory_layer") != "knowledge":
        raise BundleError(f"slice memory_layer must be 'knowledge': {src}")

    sid = fm.get("slice_id")
    sid_str = str(sid).strip() if sid is not None else ""
    if not sid_str:
        raise BundleError(f"slice_id missing in frontmatter: {src}")

    session = fm.get("distilled_from")
    session_str = str(session).strip() if session is not None else None
    if session_str == "":
        session_str = None

    return sid_str, src_resolved, session_str


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
    knowledge_root = (memory_root / "knowledge").resolve(strict=False)

    slice_infos: list[tuple[str, Path, str | None]] = []
    seen: dict[str, Path] = {}
    sessions: set[str] = set()

    for src in slice_paths:
        sid, src_resolved, session = _validated_slice_info(knowledge_root, src)
        if sid in seen:
            raise BundleError(
                f"duplicate slice_id '{sid}' selected in {seen[sid]!s} and {src_resolved!s}"
            )
        seen[sid] = src_resolved
        slice_infos.append((sid, src_resolved, session))
        if session:
            sessions.add(session)

    warnings: list[str] = []
    if not slice_paths:
        warnings.append("empty selection")

    out_dir_resolved = out_dir.resolve(strict=False)
    if _is_within(out_dir_resolved, knowledge_root):
        raise BundleError(f"output directory must not be under knowledge root: {out_dir}")

    try:
        out_dir.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BundleError(f"failed to prepare output directory {out_dir}: {exc}") from exc

    try:
        work_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{out_dir.name}.tmp-",
                dir=str(out_dir.parent),
            )
        )
    except OSError as exc:
        raise BundleError(f"failed to prepare output directory {out_dir}: {exc}") from exc

    try:
        slices_out = work_dir / "slices"
        try:
            slices_out.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise BundleError(f"failed to create slices directory: {exc}") from exc

        slice_ids = [sid for sid, _, _ in slice_infos]
        for sid, src, _session in slice_infos:
            try:
                shutil.copyfile(src, slices_out / f"{sid}.md")
            except OSError as exc:
                raise BundleError(f"failed to copy slice '{sid}' from {src}: {exc}") from exc

        unique_slice_ids = sorted(set(slice_ids))
        slice_id_set = set(unique_slice_ids)
        node_set = {f"slice:{sid}" for sid in unique_slice_ids} | {f"session:{s}" for s in sessions}

        events: list[dict[str, Any]] = []

        try:
            lifecycle_events = lifecycle.read_events(memory_root)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            warnings.append(f"lifecycle ledger unreadable: {exc}")
            lifecycle_events = []

        for event in lifecycle_events:
            if str(event.get("record_id", "")) in slice_id_set:
                events.append({"ledger": "lifecycle", **event})

        try:
            edges = relations.read_edges(memory_root)
        except Exception as exc:
            raise BundleError(f"failed to read relations ledger: {exc}") from exc

        for edge in edges:
            if edge.get("from") in node_set or edge.get("to") in node_set:
                events.append({"ledger": "relations", **edge})

        try:
            processing_events = processing.read_events(memory_root)
        except Exception as exc:
            raise BundleError(f"failed to read processing ledger: {exc}") from exc

        for record in processing_events:
            if record.get("session_key") in sessions:
                events.append({"ledger": "processing", **record})

        ledger_path = work_dir / "ledger.jsonl"
        try:
            with ledger_path.open("w", encoding="utf-8") as handle:
                for event in events:
                    handle.write(_canonical_jsonl_line(event) + "\n")
        except OSError as exc:
            raise BundleError(f"failed to write ledger: {exc}") from exc

        manifest = {
            "generated_ts": now,
            "selection": selection,
            "slice_ids": unique_slice_ids,
            "counts": {"slices": len(unique_slice_ids), "ledger_events": len(events)},
            "raw_excluded": True,
        }
        if warnings:
            manifest["warnings"] = warnings
        try:
            (work_dir / "manifest.json").write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise BundleError(f"failed to write manifest: {exc}") from exc

        backup_dir: Path | None = None
        if out_dir.exists():
            if not out_dir.is_dir():
                raise BundleError(f"output path is not a directory: {out_dir}")
            backup_dir = out_dir.parent / f".{out_dir.name}.bak-{uuid.uuid4().hex}"
            try:
                out_dir.rename(backup_dir)
            except OSError as exc:
                raise BundleError(f"failed to stage existing output directory {out_dir}: {exc}") from exc

        try:
            work_dir.rename(out_dir)
        except OSError as exc:
            if backup_dir is not None and backup_dir.exists() and not out_dir.exists():
                try:
                    backup_dir.rename(out_dir)
                except OSError:
                    pass
            raise BundleError(f"failed to finalize output directory {out_dir}: {exc}") from exc

        if backup_dir is not None:
            try:
                shutil.rmtree(backup_dir)
            except OSError:
                pass

        return out_dir
    except Exception:
        try:
            shutil.rmtree(work_dir)
        except OSError:
            pass
        raise
