from dataclasses import dataclass
import re
import subprocess
import sys
from typing import Callable, Tuple
import unittest


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

TESTS_CORE: Tuple[str, ...] = (
    'paulshaclaw.memory.tests.test_importer_cli',
    'paulshaclaw.memory.tests.test_classifier',
    'paulshaclaw.memory.tests.test_replay_selector',
    'paulshaclaw.memory.tests.test_replay_bundle',
)

TESTS_DECAY: Tuple[str, ...] = (
    'paulshaclaw.memory.tests.test_ledger_lifecycle',
    'paulshaclaw.memory.tests.test_janitor_scanner',
    'paulshaclaw.memory.tests.test_janitor_rules',
)

TestRunner = Callable[[Tuple[str, ...]], bool]


from pathlib import Path


_REVIEW_BLOCKING_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"不可合併"),
    re.compile(r"不合併"),
    re.compile(r"阻斷"),
    re.compile(r"阻擋"),
    re.compile(r"\bdo not merge\b", re.IGNORECASE),
    re.compile(r"\bdon't merge\b", re.IGNORECASE),
    re.compile(r"\bnot ready to merge\b", re.IGNORECASE),
    re.compile(r"\bnot mergeable\b", re.IGNORECASE),
    re.compile(r"\bcannot merge\b", re.IGNORECASE),
    re.compile(r"\bcan't merge\b", re.IGNORECASE),
    re.compile(r"\bblocked\b", re.IGNORECASE),
    re.compile(r"\bblock(?:er|ers|ing)\b", re.IGNORECASE),
)

_REVIEW_NEGATIVE_APPROVAL_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\bnot approved for merge\b", re.IGNORECASE),
)

_REVIEW_CLEAR_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"可\s*合併"),
    re.compile(r"可以合併"),
    re.compile(r"\bmergeable\b", re.IGNORECASE),
    re.compile(r"\bready to merge\b", re.IGNORECASE),
    re.compile(r"\bok to merge\b", re.IGNORECASE),
    re.compile(r"\bapproved for merge\b", re.IGNORECASE),
)

_REVIEW_NEGATED_BLOCKING_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"無阻斷性問題"),
    re.compile(r"無阻擋性問題"),
    re.compile(r"\bno blocking\b", re.IGNORECASE),
    re.compile(r"\bno blockers?\b", re.IGNORECASE),
    re.compile(r"\bno blocked items?\b", re.IGNORECASE),
)

_REVIEW_CONCLUSION_HEADING = re.compile(r"^#{1,6}\s+(結論|Conclusion)\s*$")


def _is_negated_review_match(text: str, match: re.Match[str]) -> bool:
    start, end = match.span()
    for pattern in _REVIEW_NEGATED_BLOCKING_PATTERNS:
        for negated in pattern.finditer(text):
            if negated.start() <= start and end <= negated.end():
                return True
    return False


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
        try:
            content = review_file.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            return ConditionResult(
                id="review_clear",
                name="review_clear",
                passed=False,
                detail=f"unreadable review.md: {e}",
            )
        # locate canonical 結論 / Conclusion section
        lines = content.splitlines()
        concl_start = None
        for i, line in enumerate(lines):
            if _REVIEW_CONCLUSION_HEADING.fullmatch(line.strip()):
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
        for pattern in _REVIEW_NEGATIVE_APPROVAL_PATTERNS:
            match = pattern.search(concl_text)
            if not match:
                continue
            return ConditionResult(
                id="review_clear",
                name="review_clear",
                passed=False,
                detail=f"blocking: {match.group(0)}",
            )
        for pattern in _REVIEW_BLOCKING_PATTERNS:
            for match in pattern.finditer(concl_text):
                if _is_negated_review_match(concl_text, match):
                    continue
                return ConditionResult(
                    id="review_clear",
                    name="review_clear",
                    passed=False,
                    detail=f"blocking: {match.group(0)}",
                )
        for pattern in _REVIEW_CLEAR_PATTERNS:
            if pattern.search(concl_text):
                return ConditionResult(id="review_clear", name="review_clear", passed=True, detail="")
        # default fail-closed
        return ConditionResult(id="review_clear", name="review_clear", passed=False, detail="unrecognized 結論 wording")
    except Exception as e:
        return ConditionResult(id="review_clear", name="review_clear", passed=False, detail=f"error: {e}")


def _default_test_runner(modules: Tuple[str, ...]) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "unittest", *modules],
        check=False,
    )
    return result.returncode == 0


def _check_tests(*, run_tests: bool, test_runner: TestRunner) -> ConditionResult:
    if not run_tests:
        return ConditionResult(
            id="tests",
            name="tests",
            passed=False,
            detail="test execution disabled",
        )
    try:
        passed = bool(test_runner(TESTS_CORE))
    except Exception as e:
        return ConditionResult(id="tests", name="tests", passed=False, detail=f"runner error: {e}")
    if passed:
        return ConditionResult(id="tests", name="tests", passed=True, detail="")
    return ConditionResult(id="tests", name="tests", passed=False, detail="core tests failed")


def _check_decay_evidence(
    repo_root: Path,
    *,
    run_tests: bool,
    test_runner: TestRunner,
) -> ConditionResult:
    evidence = _check_evidence_present(repo_root)
    if not evidence.passed:
        return ConditionResult(
            id="decay_evidence",
            name="decay_evidence",
            passed=False,
            detail=f"missing decay evidence: {evidence.detail}",
        )
    if not run_tests:
        return ConditionResult(
            id="decay_evidence",
            name="decay_evidence",
            passed=False,
            detail="test execution disabled",
        )
    try:
        passed = bool(test_runner(TESTS_DECAY))
    except Exception as e:
        return ConditionResult(
            id="decay_evidence",
            name="decay_evidence",
            passed=False,
            detail=f"runner error: {e}",
        )
    if passed:
        return ConditionResult(id="decay_evidence", name="decay_evidence", passed=True, detail="")
    return ConditionResult(
        id="decay_evidence",
        name="decay_evidence",
        passed=False,
        detail="decay evidence tests failed",
    )


def evaluate_gate(
    repo_root: Path,
    *,
    now: str,
    run_tests: bool = True,
    test_runner: TestRunner = _default_test_runner,
) -> GateVerdict:
    conditions = (
        _check_tests(run_tests=run_tests, test_runner=test_runner),
        _check_decay_evidence(repo_root, run_tests=run_tests, test_runner=test_runner),
        _check_evidence_present(repo_root),
        _check_review_clear(repo_root),
        _check_schema_unextended(),
    )
    ok = all(condition.passed for condition in conditions)
    return GateVerdict(
        ok=ok,
        ts=now,
        conditions=conditions,
        sync_manifest=SYNC_MANIFEST if ok else (),
    )
