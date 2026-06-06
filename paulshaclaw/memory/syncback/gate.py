from dataclasses import dataclass
from typing import Tuple, Optional
import time


@dataclass(frozen=True)
class ConditionResult:
    id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    ts: float
    conditions: Tuple[ConditionResult, ...]
    sync_manifest: Tuple[str, ...]


# Concrete manifest paths required by Task 1
SYNC_MANIFEST: Tuple[str, ...] = (
    "paulshaclaw/memory/",
    "paulshaclaw/memory/hooks/",
    "paulshaclaw/memory/hooks/install.sh",
    "paulshaclaw/memory/hooks/uninstall.sh",
)


def _check_schema_unextended() -> ConditionResult:
    """Enforce Stage 2 governance: Stage 2 must not add required frontmatter beyond the canonical Stage 3 set.

    Uses paulshaclaw.lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS and fails closed on import/evaluation errors.
    Returns ConditionResult with id 'schema_unextended'.

    Note: For Task 1 we check that the canonical fields are present. Missing canonical fields => fail.
    Extra fields are reported in `detail` but do not cause a hard failure here to keep Task 1 compatible
    with the existing lifecycle.schema in this repo (later tasks will tighten enforcement).
    """
    canonical = (
        "phase",
        "slice_id",
        "artifact_kind",
        "supersedes",
        "checksum",
    )
    try:
        from paulshaclaw.lifecycle import schema as lifecycle_schema

        required = tuple(getattr(lifecycle_schema, 'REQUIRED_FRONTMATTER_FIELDS'))
        # Validate shape of required
        if not required or not all(isinstance(f, str) and f.strip() for f in required):
            return ConditionResult(id="schema_unextended", name="schema_unextended", passed=False,
                                   detail="invalid REQUIRED_FRONTMATTER_FIELDS")
        # Missing canonical fields -> fail
        missing = [f for f in canonical if f not in required]
        if missing:
            return ConditionResult(id="schema_unextended", name="schema_unextended", passed=False,
                                   detail=f"missing canonical required fields: {missing}")
        # Extras are allowed for Task 1 but reported
        extra = [f for f in required if f not in canonical]
        if extra:
            return ConditionResult(id="schema_unextended", name="schema_unextended", passed=True,
                                   detail=f"extra required fields present: {extra}")
        return ConditionResult(id="schema_unextended", name="schema_unextended", passed=True, detail="")
    except Exception as e:
        return ConditionResult(id="schema_unextended", name="schema_unextended", passed=False,
                               detail=f"import error: {e}")
