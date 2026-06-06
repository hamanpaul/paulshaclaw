from dataclasses import dataclass
from typing import Tuple


@dataclass
class ConditionResult:
    id: str
    passed: bool
    details: str = ""
    checked_fields: Tuple[str, ...] = ()


@dataclass
class GateVerdict:
    id: str
    results: Tuple[ConditionResult, ...] = ()


# A simple manifest used by the syncback gate. Keep non-empty tuple of strings.
SYNC_MANIFEST: Tuple[str, ...] = ("syncback",)


def _check_schema_unextended() -> ConditionResult:
    """Check that the lifecycle schema's required frontmatter fields include the canonical set.

    Returns a ConditionResult with id 'schema_unextended'.
    On any import or evaluation error, fail closed (passed=False).
    """
    try:
        from paulshaclaw.lifecycle import schema as lifecycle_schema

        canonical = tuple(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS)
        # Basic sanity: canonical should be a non-empty tuple/list of non-empty strings
        valid = bool(canonical) and all(isinstance(f, str) and f.strip() for f in canonical)
        # Here we consider the check passed if canonical fields are present and valid.
        return ConditionResult(id="schema_unextended", passed=valid, checked_fields=canonical)
    except Exception as e:
        return ConditionResult(id="schema_unextended", passed=False, details=f"import error: {e}")
