from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Mapping

from ..ledger import processing, relations
from . import slice_frontmatter, splitter
from .config import AtomizerConfig, is_safe_path_component
from .llm_promoter import LLMPromoter, PromoteError
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


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _archive_fragments(memory_root: Path, fragment_paths: list[Path], now: str) -> None:
    for frag_path in sorted(set(fragment_paths), key=lambda path: path.name):
        if not frag_path.exists():
            continue
        dst = memory_root / "archive" / "fragments" / _month("", now) / frag_path.name
        _move(frag_path, dst)


def _clear_cache_key(memory_root: Path, cache_key: str | None) -> None:
    if not cache_key:
        return
    if not LLMPromoter.is_valid_cache_key(cache_key):
        return
    cache_root = (memory_root / "runtime" / "cache" / "atomize").resolve()
    candidate = (cache_root / f"{cache_key}.json").resolve()
    if candidate.parent != cache_root:
        return
    try:
        candidate.unlink()
    except FileNotFoundError:
        return


def _promoter_metadata(promoter: Promoter) -> dict[str, str]:
    if isinstance(promoter, IdentityPromoter):
        return {"promoter": "identity"}
    if isinstance(promoter, LLMPromoter):
        skill_text = getattr(promoter, "_skill", "")
        return {
            "promoter": "llm",
            "model": str(getattr(promoter, "_model", "unknown")),
            "skill_hash": hashlib.sha256(skill_text.encode("utf-8")).hexdigest(),
        }
    return {}


def _fragment_refs_for_slice(
    slice_: slice_frontmatter.Slice,
    fragments_by_index: dict[int, tuple[Path, Fragment]],
    fragments_by_ref: dict[str, tuple[Path, Fragment]],
) -> list[tuple[Path, Fragment]]:
    source_fragments = slice_.frontmatter.get("source_fragments")
    if isinstance(source_fragments, list) and source_fragments:
        return [fragments_by_index[int(index)] for index in source_fragments]

    fragment_ref = slice_.frontmatter.get("fragment_ref")
    if isinstance(fragment_ref, str) and fragment_ref:
        return [fragments_by_ref[fragment_ref]]

    raise KeyError(f"slice {slice_.slice_id} is missing source fragment references")


def _prepare_slice_writes(
    promoted: list[slice_frontmatter.Slice],
    *,
    fragments_by_index: dict[int, tuple[Path, Fragment]],
    fragments_by_ref: dict[str, tuple[Path, Fragment]],
) -> list[tuple[slice_frontmatter.Slice, list[tuple[Path, Fragment]]]]:
    prepared: list[tuple[slice_frontmatter.Slice, list[tuple[Path, Fragment]]]] = []
    for slice_ in promoted:
        prepared.append(
            (
                slice_,
                _fragment_refs_for_slice(slice_, fragments_by_index, fragments_by_ref),
            )
        )
    return prepared


def _append_semantic_edges(
    memory_root: Path,
    *,
    slice_: slice_frontmatter.Slice,
    title_to_slice_id: dict[str, str],
    now: str,
    config_hash: str,
    warnings: list[str],
) -> None:
    for relation in slice_.relations:
        relation_type = relation["type"]
        if relation_type == "relates_to":
            target_title = str(relation["target_title"])
            target_slice_id = title_to_slice_id.get(target_title)
            if target_slice_id is None:
                warnings.append(
                   f"slice:{slice_.slice_id}: relates_to target_title {target_title!r} not found; edge skipped"
                )
                continue
            relations.append_edge(
                memory_root,
                type="relates_to",
                frm=f"slice:{slice_.slice_id}",
                to=f"slice:{target_slice_id}",
                now=now,
                config_hash=config_hash,
            )
            continue

        if relation_type == "mentions":
            relations.append_edge(
                memory_root,
                type="mentions",
                frm=f"slice:{slice_.slice_id}",
                to=f"entity:{relation['entity']}",
                now=now,
                config_hash=config_hash,
            )
            continue

        warnings.append(
            f"slice:{slice_.slice_id}: unsupported semantic relation type {relation_type!r}; edge skipped"
        )


def _has_unsupported_semantic_relations(promoted: list[slice_frontmatter.Slice]) -> str | None:
    for slice_ in promoted:
        for relation in slice_.relations:
            relation_type = relation.get("type") if isinstance(relation, Mapping) else None
            if relation_type not in {"relates_to", "mentions"}:
                return f"slice {slice_.slice_id} has unsupported semantic relation type: {relation_type!r}"
    return None


def _promote_fragments(
    promoter: Promoter,
    fragments: list[Fragment],
    config: AtomizerConfig,
) -> list[slice_frontmatter.Slice]:
    try:
        return promoter.promote(fragments, config)
    except PromoteError:
        raise
    except Exception as exc:
        raise PromoteError(f"unexpected promoter failure: {exc}") from exc


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
            if not is_safe_path_component(value)
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
    if not all(is_safe_path_component(value) for value in (project, agent, session)):
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
            try:
                promoted = _promote_fragments(promoter, fragments, config)
            except PromoteError as exc:
                warnings.append(f"{session_key}: {exc}; session {session_key} left in split")
                continue
            has_error = False
            for slice_ in promoted:
                errors = slice_frontmatter.validate(slice_.frontmatter, slice_.body)
                if errors:
                    warnings.append(
                        f"dry_run {session_key}: slice validation failed: {errors}; session {session_key} left in split"
                    )
                    has_error = True
                    break
            if has_error:
                continue
            slices_written += len(promoted)
        return slices_written

    events = processing.fold_events(memory_root)
    for session_key, event in events.items():
        state = str(event.get("state", ""))
        agent, _, session = session_key.partition(":")
        if not all(is_safe_path_component(value) for value in (agent, session)):
            warnings.append(f"session {session_key}: unsafe processing ledger session key; skipped")
            continue
        frag_dir_glob = sorted((memory_root / "inbox" / "_slices").rglob(f"{agent}__{session}__*.md"))
        if state == "promoted":
            cache_key = event.get("cache_key")
            _clear_cache_key(memory_root, cache_key if isinstance(cache_key, str) else None)
            if frag_dir_glob:
                _archive_fragments(memory_root, frag_dir_glob, now)
            continue
        if state != "split":
            continue
        if not frag_dir_glob:
            warnings.append(f"session {session_key}: split state has no fragment files; skipped")
            continue

        # Phase 1: Read all fragments and build candidate slices
        fragments: list[tuple[Path, Fragment]] = []
        has_error = False
        for frag_path in frag_dir_glob:
            fragment = _read_fragment(frag_path)
            if fragment is None:
                warnings.append(f"{frag_path}: unreadable fragment; session {session_key} skipped")
                has_error = True
                break
            fragments.append((frag_path, fragment))

        if has_error:
            continue

        try:
            promoted = _promote_fragments(promoter, [fragment for _, fragment in fragments], config)
        except PromoteError as exc:
            warnings.append(f"{session_key}: {exc}; session {session_key} left in split")
            continue

        # Phase 2: Validate all slices before any writes
        for slice_ in promoted:
            errors = slice_frontmatter.validate(slice_.frontmatter, slice_.body)
            if errors:
                warnings.append(
                    f"session {session_key}: slice validation failed: {errors}; session {session_key} left in split"
                )
                has_error = True
                break

        if has_error:
            continue

        # Phase 3: All validated - now write slices, relations, and archive
        fragments_by_index = {
            fragment.fragment_index: (frag_path, fragment) for frag_path, fragment in fragments
        }
        fragments_by_ref = {
            frag_path.stem: (frag_path, fragment) for frag_path, fragment in fragments
        }
        title_to_slice_id = {
            slice_.title: slice_.slice_id for slice_ in promoted if slice_.title is not None
        }
        relation_error = _has_unsupported_semantic_relations(promoted)
        if relation_error is not None:
            warnings.append(f"session {session_key}: {relation_error}; session {session_key} left in split")
            continue
        try:
            prepared_writes = _prepare_slice_writes(
                promoted,
                fragments_by_index=fragments_by_index,
                fragments_by_ref=fragments_by_ref,
            )
        except KeyError as exc:
            warnings.append(f"session {session_key}: {exc}; session {session_key} left in split")
            continue
        for slice_, referenced_fragments in prepared_writes:
            knowledge_path = (
                memory_root
                / "knowledge"
                / str(slice_.frontmatter["project"])
                / f"{slice_.slice_id}.md"
            )
            _atomic_write(knowledge_path, slice_frontmatter.render(slice_))
            for frag_path, _ in referenced_fragments:
                relations.append_edge(
                    memory_root,
                    type="promoted_to",
                    frm=f"fragment:{frag_path.stem}",
                    to=f"slice:{slice_.slice_id}",
                    now=now,
                    config_hash=config_hash,
                )
            relations.append_edge(
                memory_root,
                type="distilled_from",
                frm=f"slice:{slice_.slice_id}",
                to=f"session:{session_key}",
                now=now,
                config_hash=config_hash,
            )
            _append_semantic_edges(
                memory_root,
                slice_=slice_,
                title_to_slice_id=title_to_slice_id,
                now=now,
                config_hash=config_hash,
                warnings=warnings,
            )
            slices_written += 1

        cache_key = None
        if isinstance(promoter, LLMPromoter):
            cache_key = promoter.cache_key_for_fragments([fragment for _, fragment in fragments])
        processing.append_state(
            memory_root,
            session_key=session_key,
            state="promoted",
            now=now,
            config_hash=config_hash,
            slices=len(promoted),
            cache_key=cache_key,
            **_promoter_metadata(promoter),
        )
        _archive_fragments(memory_root, [frag_path for frag_path, _ in fragments], now)
        _clear_cache_key(memory_root, cache_key)
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
