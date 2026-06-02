from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import List, Any

_CANONICAL_KINDS = {"merge", "supersede", "contradiction"}


@dataclass
class Proposal:
    proposal_id: str
    kind: str
    status: str
    created_ts: float
    subject_slice_ids: List[str]
    detail: str
    source: str
    config_hash: str


def proposals_dir(memory_root: str | Path) -> Path:
    """Return path to runtime/proposals under memory_root."""
    return Path(memory_root) / "runtime" / "proposals"


def append(memory_root: str | Path, proposal: Proposal) -> Path:
    """Write a proposal as JSON to runtime/proposals/<proposal_id>.json"""
    d = proposals_dir(memory_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{proposal.proposal_id}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(asdict(proposal), fh, ensure_ascii=False, indent=2)
    return path


def pending(memory_root: str | Path) -> List[Any]:
    """Return list of proposal dicts whose status == 'pending'."""
    d = proposals_dir(memory_root)
    if not d.exists():
        return []
    out = []
    for p in d.glob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if data.get("status") == "pending":
            out.append(data)
    return out


def requires_approval(kind: str) -> bool:
    return kind in _CANONICAL_KINDS
