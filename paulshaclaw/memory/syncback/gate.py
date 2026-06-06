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


from pathlib import Path


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


def _check_evidence_present(repo_root: Path) -> ConditionResult:
    """Ensure required evidence files exist and are non-empty."""
    try:
        repo_root = Path(repo_root)
        evidence_paths = [
            repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory" / "evidence" / "README.md",
            repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory" / "evidence" / "stage2-integration-template.md",
        ]
        missing = []
        empty = []
        for p in evidence_paths:
            if not p.exists():
                missing.append(str(p))
            else:
                try:
                    if p.stat().st_size == 0 or not p.read_text().strip():
                        empty.append(str(p))
                except Exception:
                    empty.append(str(p))
        if missing:
            return ConditionResult(id="evidence_present", name="evidence_present", passed=False,
                                   detail=f"missing: {missing}")
        if empty:
            return ConditionResult(id="evidence_present", name="evidence_present", passed=False,
                                   detail=f"empty: {empty}")
        return ConditionResult(id="evidence_present", name="evidence_present", passed=True, detail="")
    except Exception as e:
        return ConditionResult(id="evidence_present", name="evidence_present", passed=False,
                               detail=f"error: {e}")


def _check_review_clear(repo_root: Path) -> ConditionResult:
    """Check review.md Conclusion/結論 section for mergeable conclusion.

    Fail-closed on missing/unreadable files or missing conclusion. Treat explicit negative wording as blocking.
    """
    try:
        repo_root = Path(repo_root)
        review_file = repo_root / "docs" / "superpowers" / "workstreams" / "stage2-paulsha-memory" / "review.md"
        if not review_file.exists():
            return ConditionResult(id="review_clear", name="review_clear", passed=False, detail="missing review.md")
        content = review_file.read_text(encoding='utf-8', errors='replace')
        # locate 結論 or Conclusion section
        lines = content.splitlines()
        concl_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith('##') and ('結論' in line or 'Conclusion' in line):
                concl_start = i + 1
                break
        if concl_start is None:
            return ConditionResult(id="review_clear", name="review_clear", passed=False, detail="missing 結論/结論 section")
        # collect until next heading or end
        concl_lines = []
        for line in lines[concl_start:]:
            if line.strip().startswith('#'):
                break
            if line.strip():
                concl_lines.append(line.strip())
        concl_text = '\n'.join(concl_lines)
        if not concl_text.strip():
            return ConditionResult(id="review_clear", name="review_clear", passed=False, detail="empty 結論 section")
        lower = concl_text.lower()
        # blocking keywords
        blocking = ['不可合併', '不可', '不合併', '阻斷', '阻擋', 'blocking', 'fail']
        for b in blocking:
            if b in concl_text or b in lower:
                return ConditionResult(id="review_clear", name="review_clear", passed=False, detail=f"blocking: {b}")
        # permissive keywords
        ok_words = ['可合併', 'merge', '可 合併', '可以合併']
        for ok in ok_words:
            if ok in concl_text or ok in lower:
                return ConditionResult(id="review_clear", name="review_clear", passed=True, detail="")
        # default fail-closed
        return ConditionResult(id="review_clear", name="review_clear", passed=False, detail="unrecognized 結論 wording")
    except Exception as e:
        return ConditionResult(id="review_clear", name="review_clear", passed=False, detail=f"error: {e}")
