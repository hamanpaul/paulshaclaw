from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import instruction_corpus
from . import faceout, linker, moc_builder, naming, search


def run_moc(memory_root: Path, now: str) -> dict[str, Any]:
    warnings: list[str] = []
    warnings.extend(naming.reconcile(memory_root))
    try:
        weights = linker.materialize_links(memory_root)
    except Exception as exc:  # core-state corruption (relations) -> degrade
        warnings.append(f"linker degraded: {exc}")
        weights = {}
    moc_builder.build_mocs(memory_root, now)
    faceout.mark_faceout(memory_root)
    try:
        search.build_index(memory_root, weights, doc_corpus=instruction_corpus.load_corpus())
        indexed = True
    except Exception as exc:
        warnings.append(f"search index skipped: {exc}")
        indexed = False
    return {"renamed": True, "linked": len(weights), "mocs": True,
            "faceout": True, "indexed": indexed, "warnings": warnings}
