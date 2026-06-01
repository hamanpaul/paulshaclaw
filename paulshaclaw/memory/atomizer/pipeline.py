from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from ..ledger import processing, relations
from . import slice_frontmatter, splitter
from .config import AtomizerConfig
from .promoter import IdentityPromoter, Promoter
from .splitter import Fragment


def _parse_frontmatter(text: str) -> tuple[Mapping[str, Any] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, text
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    try:
        import yaml  # type: ignore[import-not-found]
        data = yaml.safe_load(block)
    except ModuleNotFoundError:
        data = None
    if not isinstance(data, dict):
        return None, body
    return data, body


def _month(captured_at: str, now: str) -> str:
    base = captured_at if captured_at[:7].count("-") == 1 else now
    return base[:7] if len(base) >= 7 else now[:7]


def _raw_session_docs(memory_root: Path) -> list[Path]:
    inbox = memory_root / "inbox"
    slices_dir = inbox / "_slices"
    docs: list[Path] = []
    for path in sorted(inbox.rglob("*.md")):
        if slices_dir in path.parents:
            continue
        docs.append(path)
    return docs


def _safe_path_component(value: str) -> bool:
    return (
        value.strip() == value
        and value not in {"", ".", ".."}
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
    )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _split_pass(memory_root: Path, config: AtomizerConfig, config_hash: str, now: str,
                dry_run: bool, warnings: list[str]) -> tuple[int, dict[str, list[Fragment]]]:
    count = 0
    dry_run_fragments: dict[str, list[Fragment]] = {}
    for raw_path in _raw_session_docs(memory_root):
        data, body = _parse_frontmatter(raw_path.read_text(encoding="utf-8"))
        if data is None or not data.get("project") or not data.get("source_session"):
            warnings.append(f"{raw_path}: unparseable or missing project/source_session; skipped")
            continue
        agent = str(data.get("source_agent", "_unknown"))
        session = str(data["source_session"])
        project = str(data["project"])
        unsafe_fields = [
            field for field, value in (("project", project), ("source_agent", agent), ("source_session", session))
            if not _safe_path_component(value)
        ]
        if unsafe_fields:
            warnings.append(f"{raw_path}: unsafe path field(s) {', '.join(unsafe_fields)}; skipped")
            continue
        session_key = f"{agent}:{session}"
        if processing.state_of(memory_root, session_key) in {"split", "promoted"}:
            continue
        captured_at = str(data.get("captured_at", now))
        provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
        provenance = {k: str(provenance.get(k, "")) for k in ("repo", "commit", "path")}
        source_artifact = str(data.get("source_artifact", "session"))

        bodies = splitter.split(body, config)
        if dry_run:
            fragments = []
            for index, frag_body in enumerate(bodies):
                fragments.append(Fragment(
                    project=project, source_agent=agent, source_session=session,
                    source_artifact=source_artifact, captured_at=captured_at,
                    provenance=provenance, fragment_index=index, body=frag_body))
            dry_run_fragments[session_key] = fragments
            count += 1
            continue
        for index, frag_body in enumerate(bodies):
            frag_path = (memory_root / "inbox" / "_slices" / project
                         / f"{agent}__{session}__{index:03d}.md")
            _atomic_write(frag_path, _render_fragment(
                project, agent, session, source_artifact, captured_at, provenance, index, frag_body))
            relations.append_edge(memory_root, type="fragment_of",
                                  frm=f"fragment:{agent}__{session}__{index:03d}",
                                  to=f"session:{session_key}", now=now, config_hash=config_hash)
        processing.append_state(memory_root, session_key=session_key, state="split",
                                now=now, config_hash=config_hash, fragments=len(bodies))
        archive = memory_root / "archive" / "sessions" / _month(captured_at, now) / f"{agent}__{session}.md"
        _move(raw_path, archive)
        count += 1
    return count, dry_run_fragments


def _render_fragment(project, agent, session, source_artifact, captured_at, provenance, index, body) -> str:
    lines = ["---", "memory_layer: inbox", f"project: {project}",
             f"source_agent: {agent}", f"source_session: {session}",
             f"source_artifact: {source_artifact}", f"captured_at: {captured_at}",
             "provenance:", f"  repo: {provenance.get('repo', '')}",
             f"  commit: {provenance.get('commit', '')}", f"  path: {provenance.get('path', '')}",
             f"fragment_index: {index}", f"parent_session_ref: {agent}:{session}", "---"]
    return "\n".join(lines) + "\n" + body


def _read_fragment(path: Path) -> Fragment | None:
    data, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    if data is None or not data.get("project") or not data.get("source_session"):
        return None
    project = str(data["project"])
    agent = str(data.get("source_agent", "_unknown"))
    session = str(data["source_session"])
    if not all(_safe_path_component(value) for value in (project, agent, session)):
        return None
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    provenance = {k: str(provenance.get(k, "")) for k in ("repo", "commit", "path")}
    return Fragment(project=project, source_agent=agent,
                    source_session=session,
                    source_artifact=str(data.get("source_artifact", "session")),
                    captured_at=str(data.get("captured_at", "")), provenance=provenance,
                    fragment_index=int(data.get("fragment_index", 0)), body=body)


def _promote_pass(memory_root: Path, config: AtomizerConfig, config_hash: str, now: str,
                  dry_run: bool, promoter: Promoter, warnings: list[str],
                  dry_run_fragments: dict[str, list[Fragment]]) -> int:
    slices_written = 0
    
    # In dry_run mode, process the fragments from split pass
    if dry_run and dry_run_fragments:
        for session_key, fragments in dry_run_fragments.items():
            for fragment in fragments:
                slice_ = promoter.promote(fragment, config)[0]
                errors = slice_frontmatter.validate(slice_.frontmatter, slice_.body)
                if errors:
                    warnings.append(f"dry_run: slice validation failed: {errors}")
                    continue
                slices_written += 1
        return slices_written
    
    states = processing.fold_states(memory_root)
    for session_key, state in states.items():
        if state != "split":
            continue
        agent, _, session = session_key.partition(":")
        frag_dir_glob = sorted((memory_root / "inbox" / "_slices").rglob(f"{agent}__{session}__*.md"))
        if not frag_dir_glob:
            continue
        
        # Phase 1: Read all fragments and build candidate slices
        candidates: list[tuple[Path, Fragment, slice_frontmatter.Slice]] = []
        has_error = False
        for frag_path in frag_dir_glob:
            fragment = _read_fragment(frag_path)
            if fragment is None:
                warnings.append(f"{frag_path}: unreadable fragment; session {session_key} skipped")
                has_error = True
                break
            slice_ = promoter.promote(fragment, config)[0]
            candidates.append((frag_path, fragment, slice_))
        
        if has_error:
            continue
        
        # Phase 2: Validate all slices before any writes
        for frag_path, fragment, slice_ in candidates:
            errors = slice_frontmatter.validate(slice_.frontmatter, slice_.body)
            if errors:
                warnings.append(f"{frag_path}: slice validation failed: {errors}; session {session_key} left in split")
                has_error = True
                break
        
        if has_error:
            continue
        
        # Phase 3: All validated - now write slices, relations, and archive
        archived: list[Path] = []
        for frag_path, fragment, slice_ in candidates:
            knowledge_path = memory_root / "knowledge" / fragment.project / f"{slice_.slice_id}.md"
            _atomic_write(knowledge_path, slice_frontmatter.render(slice_))
            relations.append_edge(memory_root, type="promoted_to",
                                  frm=f"fragment:{frag_path.stem}", to=f"slice:{slice_.slice_id}",
                                  now=now, config_hash=config_hash)
            relations.append_edge(memory_root, type="distilled_from",
                                  frm=f"slice:{slice_.slice_id}", to=f"session:{session_key}",
                                  now=now, config_hash=config_hash)
            archived.append(frag_path)
            slices_written += 1
        
        for frag_path in archived:
            dst = memory_root / "archive" / "fragments" / _month("", now) / frag_path.name
            _move(frag_path, dst)
        processing.append_state(memory_root, session_key=session_key, state="promoted",
                                now=now, config_hash=config_hash, slices=len(archived))
    return slices_written


def run(memory_root: Path, *, config: AtomizerConfig, config_hash: str, now: str,
        dry_run: bool = False, promoter: Promoter | None = None) -> dict[str, Any]:
    promoter = promoter or IdentityPromoter()
    warnings: list[str] = []
    split, dry_run_fragments = _split_pass(memory_root, config, config_hash, now, dry_run, warnings)
    slices = _promote_pass(memory_root, config, config_hash, now, dry_run, promoter, warnings, dry_run_fragments)
    return {
        "summary": {"split_sessions": split, "slices": slices, "skipped": len(warnings),
                    "config_hash": config_hash, "dry_run": dry_run},
        "warnings": warnings,
    }
