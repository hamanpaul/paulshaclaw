from __future__ import annotations

from dataclasses import dataclass

from .models import EffectivePolicy
from .redaction import PolicyHit


@dataclass(frozen=True)
class ClassificationResult:
    level: str
    reason: str
    policy_hash: str
    source: str


def classify_artifact(
    *,
    policy: EffectivePolicy,
    project_slug: str,
    redaction_hits: tuple[PolicyHit, ...],
) -> ClassificationResult:
    if redaction_hits:
        return ClassificationResult(
            level=policy.classification.redaction_hit_default,
            reason="redaction hits present",
            policy_hash=policy.effective_policy_hash,
            source="default_rule",
        )
    default = policy.classification.project_defaults.get(project_slug)
    if default is not None:
        return ClassificationResult(default.level, default.reason, policy.effective_policy_hash, "default_rule")
    return ClassificationResult(
        policy.classification.unknown_project_default,
        "unknown project default",
        policy.effective_policy_hash,
        "default_rule",
    )
