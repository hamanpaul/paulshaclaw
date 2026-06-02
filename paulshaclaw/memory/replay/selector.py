"""Replay selector for distilled knowledge slices.

Minimal implementation used by Stage2 dream service Task 6.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from paulshaclaw.memory.ledger import relations, retrieval_set


class SelectorError(Exception):
    pass


def _frontmatter(text: str) -> Dict[str, object]:
    """Parse simple YAML-like frontmatter delimited by '---' into a dict.

    Supports simple scalars and JSON arrays (rendered by slice_frontmatter.render).
    """
    text = text or ""
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm_text = parts[1].strip()
    fm: Dict[str, object] = {}
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # Try JSON decode for lists/objects
        if val.startswith("[") or val.startswith("{"):
            try:
                fm[key] = json.loads(val)
                continue
            except Exception:
                # tolerate Python-style single-quoted lists/dicts from tests
                try:
                    fm[key] = json.loads(val.replace("'", '"'))
                    continue
                except Exception:
                    pass
        # Booleans
        if val.lower() in ("true", "false"):
            fm[key] = val.lower() == "true"
            continue
        # Quoted strings
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            fm[key] = val[1:-1]
            continue
        # Plain string or number
        fm[key] = val
    return fm


def _entity_slice_ids(memory_root: Path, entity: str) -> List[str]:
    node = f"entity:{entity}"
    edges = relations.neighbors(memory_root, node)
    ids: List[str] = []
    for e in edges:
        if e.get("type") != "mentions":
            continue
        frm = e.get("from", "")
        if frm.startswith("slice:"):
            ids.append(frm.split("slice:", 1)[1])
    return ids


def select(
    memory_root: Path,
    *,
    project: Optional[str] = None,
    tags: Optional[List[str]] = None,
    entity: Optional[str] = None,
    include_decayed: bool = False,
) -> List[Path]:
    """Select distilled slice files matching facets.

    At least one facet (project, tags, entity) is required. Facets are AND-composed.
    By default filters decayed records via retrieval_set.active_records().
    Returns list of Path objects to matching slice files under memory_root/knowledge.
    """
    if not (project or tags or entity):
        raise SelectorError("at least one facet required")

    knowledge_root = Path(memory_root) / "knowledge"
    if not knowledge_root.exists():
        return []

    # Discover slice files and parse frontmatter
    slice_map: Dict[str, Path] = {}
    fm_map: Dict[str, Dict[str, object]] = {}
    for p in sorted(knowledge_root.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        fm = _frontmatter(text)
        if fm.get("memory_layer") != "knowledge":
            continue
        sid = fm.get("slice_id")
        if not sid:
            continue
        slice_map[str(sid)] = p
        fm_map[str(sid)] = fm

    # Start with all discovered slice ids
    matched_ids = set(slice_map.keys())

    # Project facet
    if project:
        proj_matched = {sid for sid, fm in fm_map.items() if str(fm.get("project")) == str(project)}
        matched_ids &= proj_matched

    # Tags facet: any-match
    if tags:
        tags_set = set(tags)
        tags_matched = set()
        for sid, fm in fm_map.items():
            t = fm.get("tags")
            if isinstance(t, list):
                if tags_set & set(map(str, t)):
                    tags_matched.add(sid)
        matched_ids &= tags_matched

    # Entity facet
    if entity:
        entity_ids = set(_entity_slice_ids(memory_root, entity))
        matched_ids &= entity_ids

    # Apply active-set filter unless include_decayed True
    ids_list = list(matched_ids)
    if not ids_list:
        return []

    if not include_decayed:
        active = retrieval_set.active_records(memory_root, ids_list)
        ids_list = [i for i in ids_list if i in active]

    # Build paths preserving slice_map ordering
    result: List[Path] = []
    for sid, path in slice_map.items():
        if sid in ids_list:
            result.append(path)
    return result
