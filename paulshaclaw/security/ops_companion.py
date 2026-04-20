from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Callable, Iterable


GENESIS_HASH = "GENESIS"


@dataclass(frozen=True)
class ApprovalRule:
    rule_id: str
    pattern: re.Pattern[str]
    risk_level: str
    reason: str
    required_action: str


@dataclass(frozen=True)
class ApprovalDecision:
    allowed: bool
    rule_id: str
    risk_level: str
    reason: str
    required_action: str | None = None


class ApprovalGate:
    def __init__(self, rules: Iterable[ApprovalRule] | None = None) -> None:
        self._rules = tuple(rules or DEFAULT_APPROVAL_RULES)

    def evaluate(self, command: str, approval_granted: bool = False) -> ApprovalDecision:
        normalized = command.strip()
        for rule in self._rules:
            if rule.pattern.search(normalized):
                if approval_granted:
                    return ApprovalDecision(
                        allowed=True,
                        rule_id=rule.rule_id,
                        risk_level=rule.risk_level,
                        reason=f"{rule.reason}; approval granted",
                        required_action=None,
                    )
                return ApprovalDecision(
                    allowed=False,
                    rule_id=rule.rule_id,
                    risk_level=rule.risk_level,
                    reason=rule.reason,
                    required_action=rule.required_action,
                )

        return ApprovalDecision(
            allowed=True,
            rule_id="low-risk",
            risk_level="low",
            reason="command does not match high-risk approval rules",
            required_action=None,
        )


@dataclass(frozen=True)
class RedactionRule:
    rule_id: str
    pattern: re.Pattern[str]
    replacement: Callable[[re.Match[str]], str]
    classifications: tuple[str, ...]


@dataclass(frozen=True)
class RedactionResult:
    text: str
    classifications: tuple[str, ...]
    rule_hits: tuple[str, ...]


class RedactionEngine:
    def __init__(self, rules: Iterable[RedactionRule] | None = None) -> None:
        self._rules = tuple(rules or DEFAULT_REDACTION_RULES)

    def redact(self, text: str) -> RedactionResult:
        redacted = text
        classifications: set[str] = set()
        rule_hits: list[str] = []

        for rule in self._rules:
            matched = False

            def replace(match: re.Match[str]) -> str:
                nonlocal matched
                matched = True
                return rule.replacement(match)

            redacted = rule.pattern.sub(replace, redacted)
            if matched:
                rule_hits.append(rule.rule_id)
                classifications.update(rule.classifications)

        return RedactionResult(
            text=redacted,
            classifications=tuple(sorted(classifications)),
            rule_hits=tuple(rule_hits),
        )


@dataclass(frozen=True)
class AuditEntry:
    actor: str
    action: str
    target: str
    approved: bool
    classifications: tuple[str, ...]
    occurred_at: str
    previous_hash: str
    entry_hash: str

    @classmethod
    def from_record(cls, record: dict[str, object]) -> "AuditEntry":
        return cls(
            actor=str(record["actor"]),
            action=str(record["action"]),
            target=str(record["target"]),
            approved=bool(record["approved"]),
            classifications=tuple(record["classifications"]),
            occurred_at=str(record["occurred_at"]),
            previous_hash=str(record["previous_hash"]),
            entry_hash=str(record["entry_hash"]),
        )


@dataclass(frozen=True)
class AuditVerification:
    ok: bool
    broken_index: int | None
    reason: str


class AppendOnlyAuditTrail:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        approved: bool,
        classifications: Iterable[str],
    ) -> AuditEntry:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.read_entries()
        previous_hash = entries[-1].entry_hash if entries else GENESIS_HASH
        record = {
            "actor": actor,
            "action": action,
            "target": target,
            "approved": approved,
            "classifications": list(classifications),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "previous_hash": previous_hash,
        }
        record["entry_hash"] = self._entry_hash(record)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
        return AuditEntry.from_record(record)

    def read_entries(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries: list[AuditEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(AuditEntry.from_record(json.loads(line)))
        return entries

    def verify(self) -> AuditVerification:
        previous_hash = GENESIS_HASH
        for index, entry in enumerate(self.read_entries()):
            if entry.previous_hash != previous_hash:
                return AuditVerification(
                    ok=False,
                    broken_index=index,
                    reason=f"hash chain mismatch at entry {index}",
                )
            expected_hash = self._entry_hash(
                {
                    "actor": entry.actor,
                    "action": entry.action,
                    "target": entry.target,
                    "approved": entry.approved,
                    "classifications": list(entry.classifications),
                    "occurred_at": entry.occurred_at,
                    "previous_hash": entry.previous_hash,
                }
            )
            if entry.entry_hash != expected_hash:
                return AuditVerification(
                    ok=False,
                    broken_index=index,
                    reason=f"hash mismatch at entry {index}",
                )
            previous_hash = entry.entry_hash
        return AuditVerification(ok=True, broken_index=None, reason="ok")

    @staticmethod
    def _entry_hash(record: dict[str, object]) -> str:
        body = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return sha256(body.encode("utf-8")).hexdigest()


def record_approval_decision(
    *,
    audit_trail: AppendOnlyAuditTrail,
    actor: str,
    command: str,
    decision: ApprovalDecision,
) -> AuditEntry:
    verdict = "approved" if decision.allowed else "denied"
    risk_label = f"{decision.risk_level}-risk" if decision.risk_level != "low" else "low-risk"
    return audit_trail.append(
        actor=actor,
        action=f"{decision.rule_id}.{verdict}",
        target=command,
        approved=decision.allowed,
        classifications=[risk_label, decision.rule_id, verdict],
    )


DEFAULT_APPROVAL_RULES = (
    ApprovalRule(
        rule_id="ship-command",
        pattern=re.compile(r"(^|\s)/ship(\s|$)"),
        risk_level="high",
        reason="ship flow requires explicit approval before execution",
        required_action="interactive-approval",
    ),
    ApprovalRule(
        rule_id="git-push",
        pattern=re.compile(r"\bgit\s+push\b"),
        risk_level="high",
        reason="git push requires explicit approval before execution",
        required_action="explicit-approval",
    ),
    ApprovalRule(
        rule_id="deploy-command",
        pattern=re.compile(r"(^|\s)deploy(\s|$)|\b(?:kubectl|helm)\s+(?:apply|upgrade|rollout)\b"),
        risk_level="high",
        reason="deploy command requires explicit approval before execution",
        required_action="explicit-approval",
    ),
    ApprovalRule(
        rule_id="package-install",
        pattern=re.compile(r"\b(?:pip|pip3|npm|pnpm|yarn|apt|apt-get|brew|go)\s+(?:install|get|add)\b"),
        risk_level="high",
        reason="package install requires explicit approval before execution",
        required_action="explicit-approval",
    ),
    ApprovalRule(
        rule_id="remote-operation",
        pattern=re.compile(r"\b(?:ssh|scp|sftp|rsync)\b|curl\b.*\|\s*sh"),
        risk_level="high",
        reason="remote operation requires explicit approval before execution",
        required_action="explicit-approval",
    ),
)


DEFAULT_REDACTION_RULES = (
    RedactionRule(
        rule_id="bearer-token",
        pattern=re.compile(r"(?i)(authorization\s*:\s*bearer\s+)(\S+)"),
        replacement=lambda match: f"{match.group(1)}[REDACTED:TOKEN]",
        classifications=("credential", "token"),
    ),
    RedactionRule(
        rule_id="password-assignment",
        pattern=re.compile(r"(?i)\b(password)\s*=\s*([^\s]+)"),
        replacement=lambda match: f"{match.group(1)}=[REDACTED:PASSWORD]",
        classifications=("credential",),
    ),
    RedactionRule(
        rule_id="github-token",
        pattern=re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+)\b"),
        replacement=lambda _match: "[REDACTED:GITHUB_TOKEN]",
        classifications=("credential", "token"),
    ),
)
