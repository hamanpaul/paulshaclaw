"""Dream orchestrator.

Coordinates Stage 2 "dream" passes (atomize + janitor) and appends an
append-only dream run record to the dream ledger.

This module is intentionally orchestration-only: callers inject the pass
entrypoints via callables, typically partially-bound wrappers around the real
pipeline implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import uuid

from paulshaclaw.memory.ledger import dream


def _run_pass(
    name: str,
    fn: Callable[..., dict[str, Any]],
    passes: dict[str, Any],
    errors: list[dict[str, str]],
    *,
    memory_root: Path,
    now: str,
    config_hash: str,
    dry_run: bool,
) -> None:
    """Run one pass and record its result.

    Errors are captured into ``errors`` and do not stop later passes.
    """

    try:
        result = fn(memory_root, now=now, config_hash=config_hash, dry_run=dry_run)
        passes[name] = {
            "status": "ok",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001 - orchestration boundary
        errors.append(
            {
                "pass": name,
                "exc_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        passes[name] = {
            "status": "failed",
            "result": None,
        }


def _is_partial_pass_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    warnings = value.get("warnings")
    if isinstance(warnings, list) and warnings:
        return True

    summary = value.get("summary")
    if isinstance(summary, dict):
        skipped = summary.get("skipped")
        if isinstance(skipped, int) and skipped > 0:
            return True

    return False


def run_dream(
    memory_root: Path,
    *,
    atomize_fn: Callable[..., dict[str, Any]],
    janitor_fn: Callable[..., dict[str, Any]],
    now: str,
    config_hash: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run dream passes and (optionally) append a run record.

    Args:
        memory_root: Memory root directory.
        atomize_fn: Callable for the atomize pass.
        janitor_fn: Callable for the janitor pass.
        now: Timestamp string (caller-provided).
        config_hash: Dream config hash string.
        dry_run: If True, do not persist dream ledger entries.

    Returns:
        Run record mapping.
    """

    passes: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    run_id = uuid.uuid4().hex

    _run_pass(
        "atomize",
        atomize_fn,
        passes,
        errors,
        memory_root=memory_root,
        now=now,
        config_hash=config_hash,
        dry_run=dry_run,
    )
    _run_pass(
        "janitor",
        janitor_fn,
        passes,
        errors,
        memory_root=memory_root,
        now=now,
        config_hash=config_hash,
        dry_run=dry_run,
    )

    if errors:
        status = "failed"
    else:
        atomize_result = passes.get("atomize", {}).get("result")
        janitor_result = passes.get("janitor", {}).get("result")
        status = "partial" if (_is_partial_pass_result(atomize_result) or _is_partial_pass_result(janitor_result)) else "ok"

    record: dict[str, Any] = {
        "ts": now,
        "run_id": run_id,
        "status": status,
        "passes": passes,
        "errors": errors,
        "dream_config_hash": config_hash,
        "dry_run": dry_run,
    }

    if not dry_run:
        dream.append_run(memory_root, record)

    return record
