from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class PolicyAuditEvent:
    boundary: str
    component: str
    session_ref: str
    policy_version: str
    effective_policy_hash: str
    rule_id: str
    detector: str
    line_no: int
    action: str


def append_policy_audit(path: str | Path, event: PolicyAuditEvent) -> None:
    audit_path = Path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat()}
    record.update(asdict(event))
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
