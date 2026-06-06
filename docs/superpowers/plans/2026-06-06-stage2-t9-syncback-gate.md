# Stage 2 T9 Sync-back Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the documented 5-condition sync-back gate into an executable checker — `psc memory syncback check` runs the conditions and returns a structured pass/fail verdict plus a sync manifest, so the project-tuned paulsha-memory package can only be synced back to `custom-skills` once all conditions hold.

**Architecture:** A pure-ish `memory/syncback/gate.py` evaluates 5 conditions (two of which run targeted test modules via an injectable `test_runner`, the rest are file/schema inspections) and aggregates a `GateVerdict`. `memory/syncback/cli.py` exposes `psc memory syncback check`. Fail-closed (any uncertainty → that condition fails → gate fails), read-only (no copy/push), deterministic (`now` injected, `test_runner` injectable so tests never really run unittest).

**Tech Stack:** Python 3 stdlib (`subprocess`, `dataclasses`, `pathlib`, `re`), `unittest`. Reuse `paulshaclaw.lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS`, the existing test modules, and `docs/superpowers/workstreams/stage2-paulsha-memory/{evidence/,review.md}`.

---

## File Structure

- Create: `paulshaclaw/memory/syncback/__init__.py` — exports `evaluate_gate`, `GateVerdict`, `ConditionResult`.
- Create: `paulshaclaw/memory/syncback/gate.py` — `evaluate_gate(...)` + 5 condition helpers + manifest.
- Create: `paulshaclaw/memory/syncback/cli.py` — `main`/`run` for `psc memory syncback check`.
- Modify: `paulshaclaw/memory/cli.py` — register `syncback` subcommand + `_syncback` handler.
- Create: `paulshaclaw/memory/syncback/README.md`.
- Create tests: `paulshaclaw/memory/tests/test_syncback_gate.py`, `paulshaclaw/memory/tests/test_syncback_cli.py`.

**Existing symbols to reuse (do NOT re-implement):**
- `paulshaclaw/lifecycle/schema.py`: `REQUIRED_FRONTMATTER_FIELDS` (tuple incl. `slice_id`, `artifact_kind`, `supersedes`, `checksum`, `phase`).
- Evidence dir: `docs/superpowers/workstreams/stage2-paulsha-memory/evidence/` (must contain `README.md`, `stage2-integration-template.md`).
- Review file: `docs/superpowers/workstreams/stage2-paulsha-memory/review.md` (has a `## 結論` section; non-blocking when it states `可合併` and no live `阻斷性` finding).
- `paulshaclaw/memory/cli.py`: subcommands registered via `memory_subparsers.add_parser(...)` + `set_defaults(func=_handler)` (mirror `_skillopt` / `_wakeup`).

---

## Task 1: GateVerdict types + manifest + schema condition

**Files:**
- Create: `paulshaclaw/memory/syncback/__init__.py`, `paulshaclaw/memory/syncback/gate.py`
- Test: `paulshaclaw/memory/tests/test_syncback_gate.py`

- [ ] **Step 1: Write the failing test (types + schema condition + manifest)**

Create `paulshaclaw/memory/tests/test_syncback_gate.py`:

```python
import unittest
from paulshaclaw.memory.syncback.gate import (
    evaluate_gate, GateVerdict, ConditionResult, SYNC_MANIFEST, _check_schema_unextended,
)


class SchemaConditionTest(unittest.TestCase):
    def test_schema_unextended_passes_for_canonical_fields(self):
        res = _check_schema_unextended()
        self.assertIsInstance(res, ConditionResult)
        self.assertEqual(res.id, "schema_unextended")
        self.assertTrue(res.passed, res.detail)

    def test_manifest_is_nonempty_tuple_of_strings(self):
        self.assertTrue(SYNC_MANIFEST)
        self.assertTrue(all(isinstance(p, str) and p for p in SYNC_MANIFEST))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate -v`
Expected: FAIL (`ModuleNotFoundError: paulshaclaw.memory.syncback.gate`).

- [ ] **Step 3: Implement types + manifest + schema condition in `gate.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Stage 3-owned canonical required frontmatter fields. Stage 2 MUST NOT add any.
_CANONICAL_REQUIRED = {"slice_id", "artifact_kind", "supersedes", "checksum", "phase"}

# Paths that WOULD be synced back to custom-skills/paulsha-memory once the gate passes
# (this change does not perform the copy/push — manifest is informational only).
SYNC_MANIFEST: tuple[str, ...] = (
    "paulshaclaw/memory/",
    "paulshaclaw/memory/hooks/",
    "paulshaclaw/memory/hooks/install.sh",
    "paulshaclaw/memory/hooks/uninstall.sh",
)

# Default test modules per condition (run via injectable runner).
# NOTE: names verified against paulshaclaw/memory/tests/ on 2026-06-06.
TESTS_CORE = (
    "paulshaclaw.memory.tests.test_importer_cli",
    "paulshaclaw.memory.tests.test_classifier",
    "paulshaclaw.memory.tests.test_replay_selector",
    "paulshaclaw.memory.tests.test_replay_bundle",
)
TESTS_DECAY = (
    "paulshaclaw.memory.tests.test_ledger_lifecycle",
    "paulshaclaw.memory.tests.test_janitor_scanner",
    "paulshaclaw.memory.tests.test_janitor_rules",
)

EVIDENCE_DIR = "docs/superpowers/workstreams/stage2-paulsha-memory/evidence"
EVIDENCE_REQUIRED = ("README.md", "stage2-integration-template.md")
REVIEW_PATH = "docs/superpowers/workstreams/stage2-paulsha-memory/review.md"


@dataclass(frozen=True)
class ConditionResult:
    id: str
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GateVerdict:
    ok: bool
    ts: str
    conditions: tuple[ConditionResult, ...]
    sync_manifest: tuple[str, ...]


def _check_schema_unextended() -> ConditionResult:
    cid, name = "schema_unextended", "Stage 3 frontmatter schema not extended"
    try:
        from paulshaclaw.lifecycle import schema as lifecycle_schema
        required = set(lifecycle_schema.REQUIRED_FRONTMATTER_FIELDS)
    except Exception:
        return ConditionResult(cid, name, False, "could not import lifecycle.schema")
    extra = required - _CANONICAL_REQUIRED
    if extra:
        return ConditionResult(cid, name, False, f"Stage 2 added required fields: {sorted(extra)}")
    return ConditionResult(cid, name, True, "required fields within canonical set")
```

Create `paulshaclaw/memory/syncback/__init__.py`:
```python
from .gate import evaluate_gate, GateVerdict, ConditionResult, SYNC_MANIFEST

__all__ = ["evaluate_gate", "GateVerdict", "ConditionResult", "SYNC_MANIFEST"]
```

(`evaluate_gate` is added in Task 3; if running this task's test before Task 3, temporarily import only the names defined so far — or implement Task 3's `evaluate_gate` stub now. Recommended: proceed to Task 3 before running the full suite.)

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate.SchemaConditionTest -v`
Expected: PASS. (Adjust `__init__.py` to not import `evaluate_gate` until Task 3, or land Task 3 first.)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/syncback/__init__.py paulshaclaw/memory/syncback/gate.py paulshaclaw/memory/tests/test_syncback_gate.py
git commit -m "feat(syncback): gate types, manifest, schema condition"
```

---

## Task 2: File-inspection conditions (evidence + review)

**Files:**
- Modify: `paulshaclaw/memory/syncback/gate.py`
- Test: `paulshaclaw/memory/tests/test_syncback_gate.py`

- [ ] **Step 1: Add failing tests**

Append to `test_syncback_gate.py`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from paulshaclaw.memory.syncback.gate import _check_evidence_present, _check_review_clear


class FileConditionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.ev = self.root / "docs/superpowers/workstreams/stage2-paulsha-memory/evidence"
        self.ev.mkdir(parents=True)
        (self.ev / "README.md").write_text("idx\n", encoding="utf-8")
        (self.ev / "stage2-integration-template.md").write_text("tmpl\n", encoding="utf-8")
        self.review = self.root / "docs/superpowers/workstreams/stage2-paulsha-memory/review.md"
        self.review.write_text("# review\n\n## 結論\n\n- 結論：可合併。\n- 無阻斷性問題。\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_evidence_present_passes(self):
        self.assertTrue(_check_evidence_present(self.root).passed)

    def test_evidence_missing_fails_closed(self):
        (self.ev / "README.md").unlink()
        r = _check_evidence_present(self.root)
        self.assertFalse(r.passed)

    def test_evidence_empty_file_fails(self):
        (self.ev / "README.md").write_text("", encoding="utf-8")
        self.assertFalse(_check_evidence_present(self.root).passed)

    def test_review_clear_passes_on_mergeable(self):
        self.assertTrue(_check_review_clear(self.root).passed)

    def test_review_blocking_fails(self):
        self.review.write_text("# review\n\n## 結論\n\n- 結論：有阻斷性問題，不可合併。\n", encoding="utf-8")
        self.assertFalse(_check_review_clear(self.root).passed)

    def test_review_missing_section_fails_closed(self):
        self.review.write_text("# review\n\nno conclusion here\n", encoding="utf-8")
        self.assertFalse(_check_review_clear(self.root).passed)

    def test_review_missing_file_fails_closed(self):
        self.review.unlink()
        self.assertFalse(_check_review_clear(self.root).passed)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate.FileConditionTest -v`
Expected: FAIL (helpers undefined).

- [ ] **Step 3: Implement the two helpers in `gate.py`**

```python
def _check_evidence_present(repo_root: Path) -> ConditionResult:
    cid, name = "evidence_present", "evidence files present"
    ev_dir = repo_root / EVIDENCE_DIR
    missing = []
    for fname in EVIDENCE_REQUIRED:
        p = ev_dir / fname
        try:
            if not p.is_file() or not p.read_text(encoding="utf-8").strip():
                missing.append(fname)
        except Exception:
            missing.append(fname)
    if missing:
        return ConditionResult(cid, name, False, f"missing/empty evidence: {missing}")
    return ConditionResult(cid, name, True, f"all evidence present ({len(EVIDENCE_REQUIRED)})")


def _check_review_clear(repo_root: Path) -> ConditionResult:
    cid, name = "review_clear", "review.md has a non-blocking conclusion"
    path = repo_root / REVIEW_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ConditionResult(cid, name, False, "review.md unreadable/missing")

    # Extract the 結論 / Conclusion section (to end of doc).
    m = re.search(r"^##\s*(結論|Conclusion)\b", text, re.MULTILINE)
    if not m:
        return ConditionResult(cid, name, False, "no 結論/Conclusion section")
    section = text[m.start():]

    # Fail-closed: a live blocking marker not negated by 無/no.
    if re.search(r"(?<!無)\s*阻斷性", section) or re.search(r"\bBLOCK(?:ER|ING)\b", section, re.IGNORECASE):
        # allow the explicit non-blocking phrasing "無阻斷性"
        if "無阻斷性" not in section and "no blocking" not in section.lower():
            return ConditionResult(cid, name, False, "blocking finding present in conclusion")
    # Require an explicit mergeable verdict.
    if "可合併" in section or re.search(r"\bmergeable\b", section, re.IGNORECASE):
        return ConditionResult(cid, name, True, "conclusion is mergeable, no blocking finding")
    return ConditionResult(cid, name, False, "no explicit mergeable verdict")
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate.FileConditionTest -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/syncback/gate.py paulshaclaw/memory/tests/test_syncback_gate.py
git commit -m "feat(syncback): evidence + review conditions (fail-closed)"
```

---

## Task 3: Test-running conditions + evaluate_gate aggregation

**Files:**
- Modify: `paulshaclaw/memory/syncback/gate.py`
- Test: `paulshaclaw/memory/tests/test_syncback_gate.py`

The `test_runner` is injectable: `Callable[[tuple[str, ...]], bool]` returning True on all-pass. Default runs `python3 -m unittest <modules>` via subprocess. Tests inject a fake so unittest is never really invoked.

- [ ] **Step 1: Add failing tests**

Append to `test_syncback_gate.py`:

```python
class EvaluateGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        ev = self.root / "docs/superpowers/workstreams/stage2-paulsha-memory/evidence"
        ev.mkdir(parents=True)
        (ev / "README.md").write_text("idx\n", encoding="utf-8")
        (ev / "stage2-integration-template.md").write_text("tmpl\n", encoding="utf-8")
        (self.root / "docs/superpowers/workstreams/stage2-paulsha-memory/review.md").write_text(
            "## 結論\n- 結論：可合併。\n- 無阻斷性問題。\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_pass_yields_ok_and_manifest(self):
        v = evaluate_gate(self.root, now="2026-06-06T00:00:00Z", test_runner=lambda mods: True)
        self.assertTrue(v.ok, [c for c in v.conditions if not c.passed])
        self.assertEqual(v.ts, "2026-06-06T00:00:00Z")
        self.assertTrue(v.sync_manifest)
        self.assertEqual({c.id for c in v.conditions},
                         {"tests", "decay_evidence", "evidence_present", "review_clear", "schema_unextended"})

    def test_failing_tests_make_gate_fail_and_empty_manifest(self):
        v = evaluate_gate(self.root, now="t", test_runner=lambda mods: False)
        self.assertFalse(v.ok)
        self.assertEqual(v.sync_manifest, ())
        self.assertFalse(next(c for c in v.conditions if c.id == "tests").passed)

    def test_runner_exception_fails_closed(self):
        def boom(mods):
            raise RuntimeError("runner boom")
        v = evaluate_gate(self.root, now="t", test_runner=boom)
        self.assertFalse(v.ok)
        self.assertFalse(next(c for c in v.conditions if c.id == "tests").passed)

    def test_run_tests_false_marks_test_conditions_failed(self):
        # governance: skipping tests is not allowed -> the test conditions fail
        v = evaluate_gate(self.root, now="t", run_tests=False, test_runner=lambda mods: True)
        self.assertFalse(v.ok)
        self.assertFalse(next(c for c in v.conditions if c.id == "tests").passed)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate.EvaluateGateTest -v`
Expected: FAIL (`evaluate_gate` undefined).

- [ ] **Step 3: Implement runner + aggregation in `gate.py`**

```python
import subprocess
import sys


def _default_test_runner(modules: tuple[str, ...]) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *modules],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _check_tests(cid: str, name: str, modules: tuple[str, ...], *,
                 run_tests: bool, runner: Callable[[tuple[str, ...]], bool]) -> ConditionResult:
    if not run_tests:
        return ConditionResult(cid, name, False, "tests skipped (run_tests=False); governance requires running")
    try:
        ok = bool(runner(modules))
    except Exception:
        return ConditionResult(cid, name, False, "test runner raised")
    return ConditionResult(cid, name, ok, "all passed" if ok else "one or more tests failed")


def _check_decay_evidence(repo_root: Path, *, run_tests: bool,
                          runner: Callable[[tuple[str, ...]], bool]) -> ConditionResult:
    # decayed/reactivation rules: run the relevant tests AND require evidence dir present.
    t = _check_tests("decay_evidence", "decayed/reactivation rules + evidence",
                     TESTS_DECAY, run_tests=run_tests, runner=runner)
    if not t.passed:
        return t
    ev = _check_evidence_present(repo_root)
    if not ev.passed:
        return ConditionResult("decay_evidence", t.name, False, f"evidence missing: {ev.detail}")
    return ConditionResult("decay_evidence", t.name, True, "tests passed and evidence present")


def evaluate_gate(
    repo_root,
    *,
    now: str,
    run_tests: bool = True,
    test_runner: Callable[[tuple[str, ...]], bool] = _default_test_runner,
) -> GateVerdict:
    repo_root = Path(repo_root)
    conditions = (
        _check_tests("tests", "importer/classifier/replay tests pass",
                     TESTS_CORE, run_tests=run_tests, runner=test_runner),
        _check_decay_evidence(repo_root, run_tests=run_tests, runner=test_runner),
        _check_evidence_present(repo_root),
        _check_review_clear(repo_root),
        _check_schema_unextended(),
    )
    ok = all(c.passed for c in conditions)
    return GateVerdict(
        ok=ok, ts=now, conditions=conditions,
        sync_manifest=SYNC_MANIFEST if ok else (),
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate.EvaluateGateTest -v`
Expected: PASS. Then run the whole module: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_gate -v` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/syncback/gate.py paulshaclaw/memory/tests/test_syncback_gate.py
git commit -m "feat(syncback): test-running conditions + evaluate_gate aggregation"
```

---

## Task 4: CLI + subcommand registration

**Files:**
- Create: `paulshaclaw/memory/syncback/cli.py`
- Modify: `paulshaclaw/memory/cli.py`
- Test: `paulshaclaw/memory/tests/test_syncback_cli.py`

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_syncback_cli.py`:

```python
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from paulshaclaw.memory.syncback import cli


def _seed(root: Path, mergeable=True):
    ev = root / "docs/superpowers/workstreams/stage2-paulsha-memory/evidence"
    ev.mkdir(parents=True)
    (ev / "README.md").write_text("idx\n", encoding="utf-8")
    (ev / "stage2-integration-template.md").write_text("t\n", encoding="utf-8")
    concl = "可合併。\n- 無阻斷性問題。" if mergeable else "有阻斷性問題，不可合併。"
    (root / "docs/superpowers/workstreams/stage2-paulsha-memory/review.md").write_text(
        f"## 結論\n- 結論：{concl}\n", encoding="utf-8")


class SyncbackCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(argv, _test_runner=lambda mods: True)
        return rc, buf.getvalue()

    def test_all_pass_rc0(self):
        _seed(self.root, mergeable=True)
        rc, out = self._run(["check", "--repo-root", str(self.root), "--now", "t"])
        self.assertEqual(rc, 0)
        self.assertIn("schema_unextended", out)

    def test_blocking_review_rc1(self):
        _seed(self.root, mergeable=False)
        rc, _ = self._run(["check", "--repo-root", str(self.root), "--now", "t"])
        self.assertEqual(rc, 1)

    def test_json_output(self):
        _seed(self.root, mergeable=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["check", "--repo-root", str(self.root), "--now", "t", "--json"],
                          _test_runner=lambda mods: True)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_cli -v`
Expected: FAIL (`cli` undefined).

- [ ] **Step 3: Implement `cli.py`**

```python
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from .gate import evaluate_gate


def run(args: argparse.Namespace, *, test_runner: Callable | None = None) -> int:
    now = args.now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    kwargs = {"now": now, "run_tests": not args.no_run_tests}
    if test_runner is not None:
        kwargs["test_runner"] = test_runner
    verdict = evaluate_gate(Path(args.repo_root), **kwargs)

    if args.json:
        print(json.dumps(asdict(verdict), ensure_ascii=False, sort_keys=True))
    else:
        print(f"sync-back gate: {'PASS' if verdict.ok else 'FAIL'} ({verdict.ts})")
        for c in verdict.conditions:
            print(f"  [{'x' if c.passed else ' '}] {c.id}: {c.name} — {c.detail}")
        if verdict.ok:
            print("sync manifest (NOT executed; manual sync only):")
            for p in verdict.sync_manifest:
                print(f"  - {p}")
    return 0 if verdict.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psc memory syncback")
    sub = parser.add_subparsers(dest="syncback_command", required=True)
    check = sub.add_parser("check", help="evaluate the sync-back gate")
    check.add_argument("--repo-root", default=".")
    check.add_argument("--no-run-tests", action="store_true")
    check.add_argument("--json", action="store_true")
    check.add_argument("--now", default=None)
    check.set_defaults(func=run)
    return parser


def main(argv: Sequence[str] | None = None, *, _test_runner: Callable | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(run(args, test_runner=_test_runner))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register under `psc memory`**

In `paulshaclaw/memory/cli.py`, add (mirror the `wakeup`/`skillopt` blocks):
```python
    syncback = memory_subparsers.add_parser("syncback")
    syncback_subparsers = syncback.add_subparsers(dest="syncback_command", required=True)
    syncback_check = syncback_subparsers.add_parser("check")
    syncback_check.add_argument("--repo-root", default=".")
    syncback_check.add_argument("--no-run-tests", action="store_true")
    syncback_check.add_argument("--json", action="store_true")
    syncback_check.add_argument("--now", default=None)
    syncback_check.set_defaults(func=_syncback)
```
And the handler:
```python
def _syncback(args: argparse.Namespace) -> int:
    from .syncback import cli as syncback_cli
    return syncback_cli.run(args)
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_syncback_cli -v`
Expected: PASS. Smoke: `python3 -m paulshaclaw.memory.cli memory syncback check --repo-root . --no-run-tests` → prints FAIL (tests skipped) rc 1.

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/syncback/cli.py paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_syncback_cli.py
git commit -m "feat(syncback): psc memory syncback check CLI + subcommand"
```

---

## Task 5: README, full suite, real-run sanity, policy gate

**Files:**
- Create: `paulshaclaw/memory/syncback/README.md`

- [ ] **Step 1: Write `README.md`**

Document: `psc memory syncback check` evaluates the 5 sync-back conditions and returns PASS/FAIL + a sync manifest; it is **fail-closed** (any uncertainty fails), **read-only** (never copies into staging or pushes to `hamanpaul/custom-skills` — that is a manual, separately-authorized step), and **deterministic** (`now` injected; `test_runner` injectable). List the 5 conditions and what each checks. State the sync-back entity is the installable package (memory modules + hooks + install.sh + future MCP server), not a skill.

- [ ] **Step 2: Run the full memory suite**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests`
Expected: all PASS (incl. the two new syncback test modules).

- [ ] **Step 3: Real-run sanity (verify default runner wiring)**

Run: `python3 -m paulshaclaw.memory.cli memory syncback check --repo-root .`
Expected: it actually runs the targeted test modules; prints a PASS/FAIL line per condition. (If the real test modules named in `TESTS_CORE`/`TESTS_DECAY` do not all exist, adjust the module tuples in `gate.py` to the actual test module names present under `paulshaclaw/memory/tests/` — verify with `ls paulshaclaw/memory/tests/`.)

- [ ] **Step 4: Run the repo policy / lint gate**

Run the repo policy check + frontmatter/policy-consumer lint as prior Stage 2 changes do. Expected: green. Branch `feature/stage2-t9-syncback-gate` satisfies R-12 (no dots).

- [ ] **Step 5: Commit docs**

```bash
git add paulshaclaw/memory/syncback/README.md
git commit -m "docs(syncback): module README (fail-closed, read-only, 5 conditions)"
```

- [ ] **Step 6: openspec-archive after merge**

After the PR merges, archive the `stage2-t9-syncback-gate` OpenSpec change into `openspec/changes/archive/` and sync its spec delta into `openspec/specs/stage2-memory-governance/spec.md`, mirroring the most recent archived Stage 2 change. Then tick T9 in the roadmap §5.4 checklist (per the maintenance rule).

---

## Self-Review notes (for the implementer)
- **Verify the test-module names** in `TESTS_CORE`/`TESTS_DECAY` against `ls paulshaclaw/memory/tests/` before relying on the real run; the gate is only meaningful if those modules exist. Tests inject a fake runner so unit tests pass regardless, but the real `check` must point at real modules.
- Fail-closed everywhere: missing file, unreadable, runner raise, no conclusion section → that condition fails → gate fails. Never default a condition to pass.
- Read-only: this change never copies into `custom-skills/paulsha-memory/` nor pushes; the manifest is informational.
- Determinism: `now` enters only at the CLI boundary; `test_runner` is injectable so the gate's own tests never invoke unittest.
- `--no-run-tests` intentionally makes the test conditions FAIL (governance can't skip tests); it exists only to inspect the other conditions quickly.
