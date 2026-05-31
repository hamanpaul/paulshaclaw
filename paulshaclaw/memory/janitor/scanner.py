"""
Janitor scanner orchestrator.

Coordinates scanning knowledge records for decay/reactivation and persists
lifecycle events.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from paulshaclaw.memory.janitor import record_source, rules
from paulshaclaw.memory.janitor.config import JanitorConfig
from paulshaclaw.memory.ledger import import_log, lifecycle


def _lifecycle_path(memory_root: Path) -> Path:
    """Get path to lifecycle ledger."""
    return memory_root / "runtime" / "ledger" / "lifecycle.jsonl"


def _build_lc_state(memory_root: Path) -> dict[str, dict[str, str]]:
    """
    Build lifecycle state mapping for rules.
    
    Converts fold_lifecycle output to rules-compatible format:
    - last_state -> state
    - last_event_ts -> since_ts
    """
    lc_path = _lifecycle_path(memory_root)
    events = lifecycle.read_events(lc_path)
    folded = lifecycle.fold_lifecycle(events)
    
    result: dict[str, dict[str, str]] = {}
    for record_id, rec in folded.items():
        state = rec.get("last_state", "active")
        if state is None:
            state = "active"
        since_ts = rec.get("last_event_ts", "")
        result[record_id] = {
            "state": state,
            "since_ts": since_ts if since_ts else ""
        }
    
    return result


def _build_import_index(memory_root: Path) -> dict[str, list[dict[str, str]]]:
    """
    Build import index mapping source_key -> import events.
    
    Reads import.jsonl and groups records by idempotency_key (which serves
    as source_key for matching with records).
    
    Returns:
        Dict mapping source_key to list of dicts with 'status' and 'recorded_at'
    """
    import_path = memory_root / "runtime" / "ledger" / "import.jsonl"
    records = import_log.read_import_records(import_path)
    
    index: dict[str, list[dict[str, str]]] = {}
    for rec in records:
        # Extract source_key from idempotency_key
        source_key = rec.get("idempotency_key")
        if not source_key:
            continue
        
        status = rec.get("status", "")
        recorded_at = rec.get("recorded_at", "")
        
        if source_key not in index:
            index[source_key] = []
        
        index[source_key].append({
            "status": status,
            "recorded_at": recorded_at
        })
    
    return index


def _persist_event(memory_root: Path, event: dict[str, Any]) -> None:
    """
    Persist a rules event to lifecycle ledger.
    
    Converts rules event format to lifecycle.append_event arguments.
    """
    lc_path = _lifecycle_path(memory_root)
    
    # Extract metadata fields
    metadata = {
        "schema_version": event.get("schema_version", "1"),
        "detail": event.get("detail", {}),
        "janitor_config_hash": event.get("janitor_config_hash", ""),
    }
    
    # Add event-type-specific fields to metadata
    if "original_ref" in event:
        metadata["original_ref"] = event["original_ref"]
    if "agent_ref" in event:
        metadata["agent_ref"] = event["agent_ref"]
    
    lifecycle.append_event(
        path=lc_path,
        record_id=event["record_id"],
        event_type=event["event_type"],
        source="janitor",
        reason=event["reason"],
        actor="janitor",
        run_id=None,
        metadata=metadata,
    )


def run_scan(
    memory_root: Path,
    knowledge_root: Path,
    config: JanitorConfig,
    config_hash: str,
    now: str,
    dry_run: bool = False,
    source_path_exists: Callable[[record_source.KnowledgeRecord], bool | None] | None = None
) -> dict[str, Any]:
    """
    Run janitor scan: evaluate records and persist lifecycle events.
    
    Args:
        memory_root: Memory root directory
        knowledge_root: Knowledge layer root directory
        config: Janitor configuration
        config_hash: Hash of janitor config
        now: Current timestamp (ISO format)
        dry_run: If True, compute plan but don't persist events
        source_path_exists: Optional callable to check source path existence
    
    Returns:
        Dict with keys:
            - summary: Dict with scanned/decayed/reactivated/unchanged/skipped counts
            - plan: List of planned events (if dry_run=True)
            - warnings: List of warning strings
    """
    # Load records
    records, warnings = record_source.iter_records(knowledge_root)
    
    # Build lifecycle state
    lc_state = _build_lc_state(memory_root)
    
    # Build import index
    import_index = _build_import_index(memory_root)
    
    # Plan scan
    if source_path_exists is None:
        events = rules.plan_scan(records, import_index, lc_state, config, now, config_hash)
    else:
        events = rules.plan_scan(records, import_index, lc_state, config, now, config_hash, source_path_exists)
    
    # Count event types
    decayed_count = sum(1 for e in events if e["event_type"] == "decayed")
    reactivated_count = sum(1 for e in events if e["event_type"] == "reactivation")
    scanned_count = len(records)
    unchanged_count = scanned_count - decayed_count - reactivated_count
    
    summary = {
        "scanned": scanned_count,
        "decayed": decayed_count,
        "reactivated": reactivated_count,
        "unchanged": unchanged_count,
        "skipped": 0,
        "config_hash": config_hash,
        "dry_run": dry_run,
    }
    
    result: dict[str, Any] = {
        "summary": summary,
        "plan": events if dry_run else [],
        "warnings": warnings,
    }
    
    # Persist events if not dry_run
    if not dry_run:
        for event in events:
            _persist_event(memory_root, event)
    
    return result
