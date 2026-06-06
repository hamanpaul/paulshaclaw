from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ConditionResult:
    id: str
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    ts: str
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
    canonical = {
        "phase",
        "project",
        "slice_id",
        "artifact_kind",
        "version",
        "created_at",
        "created_by",
        "source_session",
        "gate_required",
        "supersedes",
        "checksum",
    }
    try:
        from paulshaclaw.lifecycle import schema as lifecycle_schema

        required = tuple(getattr(lifecycle_schema, 'REQUIRED_FRONTMATTER_FIELDS'))
        if not required or not all(isinstance(f, str) and f.strip() for f in required):
            return ConditionResult(id="schema_unextended", name="schema_unextended", passed=False,
                                   detail="invalid REQUIRED_FRONTMATTER_FIELDS")
        required_set = set(required)
        missing = sorted(canonical - required_set)
        extra = sorted(required_set - canonical)
        if missing or extra:
            detail_parts = []
            if missing:
                detail_parts.append(f"missing required fields: {missing}")
            if extra:
                detail_parts.append(f"extra required fields: {extra}")
            return ConditionResult(
                id="schema_unextended",
                name="schema_unextended",
                passed=False,
                detail="; ".join(detail_parts),
            )
        return ConditionResult(id="schema_unextended", name="schema_unextended", passed=True, detail="")
    except Exception as e:
        return ConditionResult(id="schema_unextended", name="schema_unextended", passed=False,
                               detail=f"import error: {e}")
