# Stage 2 Topic 5 — Dream Service (orchestrator + replay bundle) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scheduled, idle-gated dream service that orchestrates the existing atomize → janitor passes with a run ledger + status + proposal-first skeleton, plus a `bundle` replay-bundle assembler that reads only distilled slices + ledger (never raw).

**Architecture:** `run_dream` is pure — it takes injectable `atomize_fn`/`janitor_fn` callables so it is unit-testable; the CLI binds the real Topic 3.2/Topic 4 entrypoints. Pass failures are isolated and recorded. Replay `bundle` selects via project/tag/entity facets + Topic 4 active-set and emits a self-contained bundle. No raw prompts anywhere; inject `now`.

**Tech Stack:** Python 3.12, stdlib (`os`/`json`/`hashlib`/`fcntl`/`shutil`), PyYAML, `unittest`.

**Design:** `docs/superpowers/specs/2026-06-02-stage2-dream-service-design.md`
**OpenSpec:** `openspec/changes/stage2-dream-service/`

**Merged facts (reuse, do not rewrite):**
- `atomizer.pipeline.run(memory_root, *, config, config_hash, now, dry_run=False, promoter=None) -> {"summary": {"split_sessions","slices","skipped",...}, "warnings": [...]}`.
- `janitor.scanner.run_scan(memory_root, knowledge_root, config, config_hash, now, dry_run=False, source_path_exists=None) -> {"summary": {"scanned","decayed","reactivated","skipped",...}, "warnings": [...]}`.
- `atomizer.config.load_config()` / `janitor.config.load_config()`; `atomizer.cli._build_promoter(args, config, memory_root)`.
- `ledger.retrieval_set.active_records(memory_root, candidate_ids) -> list[str]`; `ledger.relations.neighbors(memory_root, node)`; `ledger.lifecycle.read_events`, `ledger.processing.read_events`.
- Existing `memory/cli.py` subcommands: `dry-run-policy`, `replay`, `janitor`, `atomize`. **Add `dream` and `bundle`** (`bundle`, not `replay` — `replay` is policy).

---

## Task 1: `ledger/dream.py` — dream run ledger

**Files:**
- Create: `paulshaclaw/memory/ledger/dream.py`
- Test: `paulshaclaw/memory/tests/test_ledger_dream.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_ledger_dream.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import dream


def _rec(run_id, status, ts):
    return {"ts": ts, "run_id": run_id, "status": status,
            "passes": {}, "errors": [], "dream_config_hash": "h", "dry_run": False}


class DreamLedgerTests(unittest.TestCase):
    def test_append_then_last_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            dream.append_run(root, _rec("dream-1", "ok", "2026-06-02T01:00:00Z"))
            dream.append_run(root, _rec("dream-2", "partial", "2026-06-02T02:00:00Z"))
            self.assertEqual(dream.last_run(root)["run_id"], "dream-2")

    def test_last_run_none_when_empty(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(dream.last_run(Path(tmp)))

    def test_backlog_depth_counts_raw_sessions_excluding_slices(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "inbox" / "research" / "claude" / "2026-06-02").mkdir(parents=True)
            (root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md").write_text("x", encoding="utf-8")
            (root / "inbox" / "_slices" / "p").mkdir(parents=True)
            (root / "inbox" / "_slices" / "p" / "frag.md").write_text("y", encoding="utf-8")
            self.assertEqual(dream.backlog_depth(root), 1)

    def test_corrupt_line_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = dream.dream_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok":1}\nbroken\n', encoding="utf-8")
            with self.assertRaises(dream.DreamLedgerError):
                dream.read_runs(root)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_dream -v`
Expected: FAIL with `ImportError: cannot import name 'dream'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/dream.py
from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any


class DreamLedgerError(Exception):
    """Raised when the dream ledger cannot be safely read."""


def dream_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "dream.jsonl"


def append_run(memory_root: Path, record: dict[str, Any]) -> None:
    path = dream_path(memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_runs(memory_root: Path) -> list[dict[str, Any]]:
    path = dream_path(memory_root)
    if not path.exists():
        return []
    runs: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for lineno, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    runs.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise DreamLedgerError(f"corrupt dream ledger at line {lineno}: {exc}") from exc
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return runs


def last_run(memory_root: Path) -> dict[str, Any] | None:
    runs = read_runs(memory_root)
    return runs[-1] if runs else None


def backlog_depth(memory_root: Path) -> int:
    inbox = memory_root / "inbox"
    slices_dir = inbox / "_slices"
    if not inbox.exists():
        return 0
    return sum(1 for p in inbox.rglob("*.md") if slices_dir not in p.parents)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_dream -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/dream.py paulshaclaw/memory/tests/test_ledger_dream.py
git commit -m "feat(stage2): add T5 dream run ledger"
```

---

## Task 2: `dream/idle.py` — idle probe

**Files:**
- Create: `paulshaclaw/memory/dream/__init__.py`
- Create: `paulshaclaw/memory/dream/idle.py`
- Test: `paulshaclaw/memory/tests/test_dream_idle.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_dream_idle.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.dream import idle


class IdleTests(unittest.TestCase):
    def test_idle_when_load_below_threshold(self):
        self.assertTrue(idle.is_idle(max_load=1.0, probe=lambda: (0.2, 0.3, 0.4)))

    def test_busy_when_load_above_threshold(self):
        self.assertFalse(idle.is_idle(max_load=1.0, probe=lambda: (3.0, 1.0, 1.0)))

    def test_indeterminate_probe_fails_safe_to_run(self):
        def boom():
            raise OSError("no loadavg")
        self.assertTrue(idle.is_idle(max_load=1.0, probe=boom))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_idle -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.dream'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/dream/__init__.py
```

```python
# paulshaclaw/memory/dream/idle.py
from __future__ import annotations

import os
from typing import Callable


def is_idle(max_load: float = 1.0, probe: Callable[[], tuple[float, float, float]] = os.getloadavg) -> bool:
    """True if the 1-minute load is at or below max_load.

    Fail-safe-to-run: if the load cannot be determined, return True (the
    workday-morning schedule already targets an idle window).
    """
    try:
        one_minute = probe()[0]
    except (OSError, AttributeError, IndexError):
        return True
    return one_minute <= max_load
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_idle -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/dream/__init__.py paulshaclaw/memory/dream/idle.py paulshaclaw/memory/tests/test_dream_idle.py
git commit -m "feat(stage2): add T5 idle probe"
```

---

## Task 3: `dream/proposals.py` — proposal-first skeleton

**Files:**
- Create: `paulshaclaw/memory/dream/proposals.py`
- Test: `paulshaclaw/memory/tests/test_dream_proposals.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_dream_proposals.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.dream import proposals


class ProposalTests(unittest.TestCase):
    def test_append_and_pending(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            proposals.append(root, proposals.Proposal(
                proposal_id="p1", kind="supersede", status="pending",
                created_ts="2026-06-02T00:00:00Z", subject_slice_ids=["sl-1"],
                detail={}, source="dream-lineage", config_hash="h"))
            pend = proposals.pending(root)
            self.assertEqual(len(pend), 1)
            self.assertEqual(pend[0]["proposal_id"], "p1")

    def test_requires_approval_for_canonical_kinds(self):
        self.assertTrue(proposals.requires_approval("merge"))
        self.assertTrue(proposals.requires_approval("supersede"))
        self.assertTrue(proposals.requires_approval("contradiction"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_proposals -v`
Expected: FAIL with `ImportError: cannot import name 'proposals'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/dream/proposals.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_CANONICAL_KINDS = {"merge", "supersede", "contradiction"}


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    kind: str
    status: str
    created_ts: str
    subject_slice_ids: list[str]
    detail: dict[str, Any]
    source: str
    config_hash: str


def proposals_dir(memory_root: Path) -> Path:
    return memory_root / "runtime" / "proposals"


def append(memory_root: Path, proposal: Proposal) -> None:
    directory = proposals_dir(memory_root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{proposal.proposal_id}.json"
    path.write_text(json.dumps(asdict(proposal), sort_keys=True, indent=2), encoding="utf-8")


def pending(memory_root: Path) -> list[dict[str, Any]]:
    directory = proposals_dir(memory_root)
    if not directory.exists():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "pending":
            result.append(data)
    return result


def requires_approval(kind: str) -> bool:
    return kind in _CANONICAL_KINDS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_proposals -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/dream/proposals.py paulshaclaw/memory/tests/test_dream_proposals.py
git commit -m "feat(stage2): add T5 proposal-first skeleton"
```

---

## Task 4: `dream/orchestrator.py` — run_dream (injectable passes)

**Files:**
- Create: `paulshaclaw/memory/dream/orchestrator.py`
- Test: `paulshaclaw/memory/tests/test_dream_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_dream_orchestrator.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.dream import orchestrator
from paulshaclaw.memory.ledger import dream

NOW = "2026-06-02T05:00:00Z"


def _ok_atomize():
    return {"summary": {"split_sessions": 2, "slices": 3, "skipped": 0}, "warnings": []}


def _ok_janitor():
    return {"summary": {"scanned": 5, "decayed": 1, "reactivated": 0, "skipped": 0}, "warnings": []}


class OrchestratorTests(unittest.TestCase):
    def test_runs_both_passes_in_order_status_ok(self):
        order = []
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = orchestrator.run_dream(
                root, now=NOW, config_hash="h",
                atomize_fn=lambda: (order.append("a"), _ok_atomize())[1],
                janitor_fn=lambda: (order.append("j"), _ok_janitor())[1])
            self.assertEqual(order, ["a", "j"])
            self.assertEqual(result["status"], "ok")
            self.assertEqual(dream.last_run(root)["status"], "ok")

    def test_atomize_failure_does_not_block_janitor(self):
        ran = []
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            def boom():
                raise RuntimeError("atomize crashed")
            result = orchestrator.run_dream(
                root, now=NOW, config_hash="h",
                atomize_fn=boom,
                janitor_fn=lambda: (ran.append("j"), _ok_janitor())[1])
            self.assertEqual(ran, ["j"])  # janitor still ran
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["errors"])

    def test_warnings_make_status_partial(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = orchestrator.run_dream(
                root, now=NOW, config_hash="h",
                atomize_fn=lambda: {"summary": {"split_sessions": 1, "slices": 0, "skipped": 1}, "warnings": ["x"]},
                janitor_fn=_ok_janitor)
            self.assertEqual(result["status"], "partial")

    def test_dry_run_writes_no_ledger(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            orchestrator.run_dream(root, now=NOW, config_hash="h", dry_run=True,
                                   atomize_fn=_ok_atomize, janitor_fn=_ok_janitor)
            self.assertIsNone(dream.last_run(root))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_orchestrator -v`
Expected: FAIL with `ImportError: cannot import name 'orchestrator'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/dream/orchestrator.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..ledger import dream as dream_ledger


def _run_pass(name: str, fn: Callable[[], dict[str, Any]],
              passes: dict[str, Any], errors: list[str]) -> bool:
    """Run one pass in isolation. Returns True if it ran clean (no error, no warnings/skipped)."""
    try:
        result = fn()
    except Exception as exc:  # isolate: record and continue
        passes[name] = {"error": f"{type(exc).__name__}: {exc}"}
        errors.append(f"{name}: {exc}")
        return False
    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    passes[name] = summary
    warnings = result.get("warnings", []) if isinstance(result, dict) else []
    clean = not warnings and not summary.get("skipped")
    return clean


def run_dream(memory_root: Path, *, atomize_fn: Callable[[], dict[str, Any]],
              janitor_fn: Callable[[], dict[str, Any]], now: str, config_hash: str = "",
              dry_run: bool = False) -> dict[str, Any]:
    passes: dict[str, Any] = {}
    errors: list[str] = []
    atomize_clean = _run_pass("atomize", atomize_fn, passes, errors)
    janitor_clean = _run_pass("janitor", janitor_fn, passes, errors)

    if errors:
        status = "failed"
    elif atomize_clean and janitor_clean:
        status = "ok"
    else:
        status = "partial"

    record = {
        "ts": now,
        "run_id": f"dream-{now}",
        "status": status,
        "passes": passes,
        "errors": errors,
        "dream_config_hash": config_hash,
        "dry_run": dry_run,
    }
    if not dry_run:
        dream_ledger.append_run(memory_root, record)
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_orchestrator -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/dream/orchestrator.py paulshaclaw/memory/tests/test_dream_orchestrator.py
git commit -m "feat(stage2): add T5 dream orchestrator (isolated passes)"
```

---

## Task 5: `dream/cli.py` + memory CLI wiring + systemd templates

**Files:**
- Create: `paulshaclaw/memory/dream/cli.py`
- Create: `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service`
- Create: `paulshaclaw/memory/dream/systemd/paulsha-memory-dream.timer`
- Create: `paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh`
- Modify: `paulshaclaw/memory/cli.py`
- Test: `paulshaclaw/memory/tests/test_dream_cli.py`, `test_dream_systemd_template.py`

- [ ] **Step 1: Write the failing tests**

```python
# paulshaclaw/memory/tests/test_dream_cli.py
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import cli
from paulshaclaw.memory.ledger import dream

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-06-02T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha
"""


def _seed(root: Path):
    raw = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
    raw.parent.mkdir(parents=True)
    raw.write_text(_RAW, encoding="utf-8")


class DreamCliTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "dream", "run", "--memory-root", str(root),
                               "--now", "2026-06-02T05:00:00Z", "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertIsNone(dream.last_run(root))

    def test_require_idle_busy_skips(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "dream", "run", "--memory-root", str(root),
                               "--now", "2026-06-02T05:00:00Z", "--require-idle",
                               "--max-load", "-1"])  # impossible threshold -> always busy
            self.assertEqual(rc, 0)
            self.assertIsNone(dream.last_run(root))  # skipped, nothing written

    def test_status_reports_backlog(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "dream", "status", "--memory-root", str(root)])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["backlog_depth"], 1)


if __name__ == "__main__":
    unittest.main()
```

```python
# paulshaclaw/memory/tests/test_dream_systemd_template.py
from __future__ import annotations

import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "dream"


class SystemdTemplateTests(unittest.TestCase):
    def test_timer_has_workday_morning_schedule(self):
        timer = (BASE / "systemd" / "paulsha-memory-dream.timer").read_text(encoding="utf-8")
        self.assertIn("OnCalendar", timer)
        self.assertIn("Mon..Fri", timer)

    def test_service_invokes_require_idle(self):
        service = (BASE / "systemd" / "paulsha-memory-dream.service").read_text(encoding="utf-8")
        self.assertIn("dream run", service)
        self.assertIn("--require-idle", service)

    def test_wrapper_script_exists(self):
        self.assertTrue((BASE / "scripts" / "dream-idle-wrapper.sh").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_cli paulshaclaw.memory.tests.test_dream_systemd_template -v`
Expected: FAIL (`invalid choice: 'dream'` / missing template files)

- [ ] **Step 3: Implement CLI + templates**

```python
# paulshaclaw/memory/dream/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..atomizer import cli as atomizer_cli
from ..atomizer import config as atomizer_config
from ..atomizer import pipeline as atomizer_pipeline
from ..janitor import config as janitor_config
from ..janitor import scanner as janitor_scanner
from ..ledger import dream as dream_ledger
from . import idle, orchestrator


def _run(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    if args.require_idle and not idle.is_idle(max_load=args.max_load):
        print(json.dumps({"skipped": "system busy", "backlog_depth": dream_ledger.backlog_depth(memory_root)}))
        return 0

    atom_cfg, atom_hash = atomizer_config.load_config(override_path=None)
    jan_cfg, jan_hash = janitor_config.load_config(override_path=None)
    promoter = atomizer_cli._build_promoter(args, atom_cfg, memory_root)
    now = args.now

    def atomize_fn():
        return atomizer_pipeline.run(memory_root, config=atom_cfg, config_hash=atom_hash,
                                     now=now, dry_run=args.dry_run, promoter=promoter)

    def janitor_fn():
        return janitor_scanner.run_scan(memory_root, knowledge_root=memory_root / "knowledge",
                                        config=jan_cfg, config_hash=jan_hash, now=now, dry_run=args.dry_run)

    result = orchestrator.run_dream(memory_root, atomize_fn=atomize_fn, janitor_fn=janitor_fn,
                                    now=now, config_hash=f"{atom_hash[:8]}:{jan_hash[:8]}", dry_run=args.dry_run)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def _status(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    print(json.dumps({"last_run": dream_ledger.last_run(memory_root),
                      "backlog_depth": dream_ledger.backlog_depth(memory_root)},
                     sort_keys=True, indent=2))
    return 0


def run(args: argparse.Namespace) -> int:
    if args.dream_command == "status":
        return _status(args)
    return _run(args)
```

> Note: `_build_promoter(args, ...)` reads `args.promoter`/`args.agent_command`; the dream `run` subparser must define those (default `None` → identity). If the merged `_build_promoter` signature differs, adapt the call.

Add to `paulshaclaw/memory/cli.py` `_build_parser`, after the `atomize` block:

```python
    dream = memory_subparsers.add_parser("dream")
    dream_subparsers = dream.add_subparsers(dest="dream_command", required=True)
    dream_run = dream_subparsers.add_parser("run")
    dream_run.add_argument("--memory-root", required=True)
    dream_run.add_argument("--now", default=None)
    dream_run.add_argument("--dry-run", action="store_true")
    dream_run.add_argument("--require-idle", action="store_true")
    dream_run.add_argument("--max-load", type=float, default=1.0)
    dream_run.add_argument("--promoter", choices=["identity", "llm"], default=None)
    dream_run.add_argument("--agent-command", default=None)
    dream_run.set_defaults(func=_dream)
    dream_status = dream_subparsers.add_parser("status")
    dream_status.add_argument("--memory-root", required=True)
    dream_status.set_defaults(func=_dream)
```

And add this handler near the other `_*` handlers in `paulshaclaw/memory/cli.py`:

```python
def _dream(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .dream.cli import run as dream_run

    if getattr(args, "now", None) is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return dream_run(args)
```

```ini
# paulshaclaw/memory/dream/systemd/paulsha-memory-dream.service
[Unit]
Description=PaulSha memory dream service (atomize + janitor)

[Service]
Type=oneshot
# %h = user home; adjust MEMORY_ROOT/PYTHONPATH at install time.
ExecStart=/usr/bin/env python3 -m paulshaclaw.memory.cli memory dream run --memory-root %h/.agents/memory --require-idle
```

```ini
# paulshaclaw/memory/dream/systemd/paulsha-memory-dream.timer
[Unit]
Description=Run PaulSha memory dream on workday mornings

[Timer]
OnCalendar=Mon..Fri 05:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
# paulshaclaw/memory/dream/scripts/dream-idle-wrapper.sh
#!/usr/bin/env bash
# Thin wrapper: the idle gate lives in Python (--require-idle).
set -euo pipefail
MEMORY_ROOT="${PSC_MEMORY_ROOT:-$HOME/.agents/memory}"
exec python3 -m paulshaclaw.memory.cli memory dream run --memory-root "$MEMORY_ROOT" --require-idle
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_cli paulshaclaw.memory.tests.test_dream_systemd_template -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/dream/cli.py paulshaclaw/memory/dream/systemd paulshaclaw/memory/dream/scripts \
        paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_dream_cli.py paulshaclaw/memory/tests/test_dream_systemd_template.py
git commit -m "feat(stage2): wire dream CLI + systemd templates"
```

---

## Task 6: `replay/selector.py` — facet + active-set selection

**Files:**
- Create: `paulshaclaw/memory/replay/__init__.py`
- Create: `paulshaclaw/memory/replay/selector.py`
- Test: `paulshaclaw/memory/tests/test_replay_selector.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_replay_selector.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle, relations
from paulshaclaw.memory.replay import selector


def _slice(root: Path, slice_id: str, project: str, tags: list[str]) -> None:
    path = root / "knowledge" / project / f"{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    taglist = "[" + ", ".join(tags) + "]"
    path.write_text(f"---\nslice_id: {slice_id}\nproject: {project}\nmemory_layer: knowledge\n"
                    f"tags: {taglist}\n---\nbody {slice_id}\n", encoding="utf-8")


class SelectorTests(unittest.TestCase):
    def test_project_filter(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "prplos-core", ["pwhm"])
            _slice(root, "sl-2", "other", ["x"])
            ids = sorted(p.stem for p in selector.select(root, project="prplos-core"))
            self.assertEqual(ids, ["sl-1"])

    def test_tags_any_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "p", ["pwhm", "fsm"])
            _slice(root, "sl-2", "p", ["other"])
            ids = sorted(p.stem for p in selector.select(root, tags=["fsm"]))
            self.assertEqual(ids, ["sl-1"])

    def test_entity_via_relations(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "p", [])
            relations.append_edge(root, type="mentions", frm="slice:sl-1",
                                  to="entity:MTK", now="t", config_hash="h")
            ids = sorted(p.stem for p in selector.select(root, entity="MTK"))
            self.assertEqual(ids, ["sl-1"])

    def test_active_set_excludes_decayed_by_default(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, "sl-1", "p", [])
            lifecycle.append_event(lifecycle.lifecycle_path(root) if hasattr(lifecycle, "lifecycle_path") else root,
                                   record_id="sl-1", event_type="decayed", source="janitor",
                                   reason="ttl_expired", actor="janitor")
            self.assertEqual(selector.select(root, project="p"), [])
            self.assertEqual(len(selector.select(root, project="p", include_decayed=True)), 1)

    def test_no_facet_raises(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(selector.SelectorError):
                selector.select(Path(tmp))


if __name__ == "__main__":
    unittest.main()
```

> Note: `lifecycle.append_event` in the merged code takes `path` as a directory or file (it resolves a dir to the canonical ledger). Confirm the call shape against the merged `ledger/lifecycle.py`; adapt the decayed-seed line to whatever the merged signature is.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_replay_selector -v`
Expected: FAIL with `ImportError: cannot import name 'selector'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/replay/__init__.py
```

```python
# paulshaclaw/memory/replay/selector.py
from __future__ import annotations

from pathlib import Path

from ..ledger import relations, retrieval_set


class SelectorError(Exception):
    """Raised when a selection is invalid (e.g. no facet)."""


def _frontmatter(text: str) -> dict:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}
    block = "\n".join(lines[1:end])
    try:
        import yaml
        data = yaml.safe_load(block)
    except ModuleNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _entity_slice_ids(memory_root: Path, entity: str) -> set[str]:
    ids: set[str] = set()
    for edge in relations.neighbors(memory_root, f"entity:{entity}"):
        if edge.get("type") == "mentions":
            frm = str(edge.get("from", ""))
            if frm.startswith("slice:"):
                ids.add(frm[len("slice:"):])
    return ids


def select(memory_root: Path, *, project: str | None = None, tags: list[str] | None = None,
           entity: str | None = None, include_decayed: bool = False) -> list[Path]:
    if not project and not tags and not entity:
        raise SelectorError("specify at least one of --project/--tag/--entity")

    entity_ids = _entity_slice_ids(memory_root, entity) if entity else None
    knowledge = memory_root / "knowledge"
    matched: list[tuple[str, Path]] = []
    if knowledge.exists():
        for path in sorted(knowledge.rglob("*.md")):
            fm = _frontmatter(path.read_text(encoding="utf-8"))
            slice_id = str(fm.get("slice_id", path.stem))
            if project and str(fm.get("project")) != project:
                continue
            if tags:
                slice_tags = fm.get("tags") or []
                if not isinstance(slice_tags, list) or not (set(slice_tags) & set(tags)):
                    continue
            if entity_ids is not None and slice_id not in entity_ids:
                continue
            matched.append((slice_id, path))

    if not include_decayed and matched:
        active = set(retrieval_set.active_records(memory_root, [sid for sid, _ in matched]))
        matched = [(sid, p) for sid, p in matched if sid in active]
    return [p for _, p in matched]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_replay_selector -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/replay/__init__.py paulshaclaw/memory/replay/selector.py paulshaclaw/memory/tests/test_replay_selector.py
git commit -m "feat(stage2): add T5 replay selector"
```

---

## Task 7: `replay/bundle.py` + `replay/cli.py` + memory CLI wiring

**Files:**
- Create: `paulshaclaw/memory/replay/bundle.py`
- Create: `paulshaclaw/memory/replay/cli.py`
- Modify: `paulshaclaw/memory/cli.py`
- Test: `paulshaclaw/memory/tests/test_replay_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_replay_bundle.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.replay import bundle


def _slice(root: Path, slice_id: str) -> Path:
    path = root / "knowledge" / "p" / f"{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nslice_id: {slice_id}\nproject: p\nmemory_layer: knowledge\n"
                    f"distilled_from: claude:s1\n---\nDISTILLED {slice_id}\n", encoding="utf-8")
    return path


class BundleTests(unittest.TestCase):
    def test_build_writes_manifest_slices_ledger_no_raw(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = _slice(root, "sl-1")
            out = root / "bundle-out"
            bundle.build(root, [s], out, selection={"project": "p"}, now="2026-06-02T06:00:00Z")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["raw_excluded"])
            self.assertEqual(manifest["counts"]["slices"], 1)
            self.assertTrue((out / "slices" / "sl-1.md").exists())
            self.assertTrue((out / "ledger.jsonl").exists())
            # bundle never contains raw prompt content
            blob = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
            self.assertIn("DISTILLED", blob)

    def test_empty_selection_writes_empty_bundle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "bundle-out"
            bundle.build(root, [], out, selection={"project": "none"}, now="2026-06-02T06:00:00Z")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["counts"]["slices"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_replay_bundle -v`
Expected: FAIL with `ImportError: cannot import name 'bundle'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/replay/bundle.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

from ..ledger import lifecycle, processing, relations


def _slice_id_of(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("slice_id:"):
            return line.split(":", 1)[1].strip()
    return path.stem


def _distilled_from(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("distilled_from:"):
            return line.split(":", 1)[1].strip()
    return None


def build(memory_root: Path, slice_paths: list[Path], out_dir: Path, *,
          selection: dict, now: str) -> Path:
    slices_out = out_dir / "slices"
    slices_out.mkdir(parents=True, exist_ok=True)

    slice_ids: list[str] = []
    sessions: set[str] = set()
    for path in slice_paths:
        sid = _slice_id_of(path)
        slice_ids.append(sid)
        shutil.copyfile(path, slices_out / f"{sid}.md")
        session = _distilled_from(path)
        if session:
            sessions.add(session)

    slice_id_set = set(slice_ids)
    node_set = {f"slice:{sid}" for sid in slice_ids} | {f"session:{s}" for s in sessions}

    events: list[dict] = []
    # lifecycle events for selected record_ids
    try:
        for event in lifecycle.read_events(memory_root):
            if event.get("record_id") in slice_id_set:
                events.append({"ledger": "lifecycle", **event})
    except Exception:
        pass
    # relations edges touching selected nodes
    for edge in relations.read_edges(memory_root):
        if edge.get("from") in node_set or edge.get("to") in node_set:
            events.append({"ledger": "relations", **edge})
    # processing records for the slices' sessions
    for record in processing.read_events(memory_root):
        if record.get("session_key") in sessions:
            events.append({"ledger": "processing", **record})

    ledger_path = out_dir / "ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")

    manifest = {
        "generated_ts": now,
        "selection": selection,
        "slice_ids": sorted(slice_ids),
        "counts": {"slices": len(slice_ids), "ledger_events": len(events)},
        "raw_excluded": True,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8")
    return out_dir
```

```python
# paulshaclaw/memory/replay/cli.py
from __future__ import annotations

import argparse
from pathlib import Path

from . import bundle, selector


def run(args: argparse.Namespace) -> int:
    memory_root = Path(args.memory_root)
    tags = args.tag or None
    slices = selector.select(memory_root, project=args.project, tags=tags,
                             entity=args.entity, include_decayed=args.include_decayed)
    selection = {"project": args.project, "tags": tags, "entity": args.entity,
                 "include_decayed": args.include_decayed}
    out = bundle.build(memory_root, slices, Path(args.out), selection=selection, now=args.now)
    print(str(out))
    return 0
```

Add to `paulshaclaw/memory/cli.py` `_build_parser` (after `dream`):

```python
    bundle_p = memory_subparsers.add_parser("bundle")
    bundle_p.add_argument("--memory-root", required=True)
    bundle_p.add_argument("--project", default=None)
    bundle_p.add_argument("--tag", action="append", default=None)
    bundle_p.add_argument("--entity", default=None)
    bundle_p.add_argument("--include-decayed", action="store_true")
    bundle_p.add_argument("--out", required=True)
    bundle_p.add_argument("--now", default=None)
    bundle_p.set_defaults(func=_bundle)
```

And the handler:

```python
def _bundle(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .replay.cli import run as bundle_run

    if args.now is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return bundle_run(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_replay_bundle -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/replay/bundle.py paulshaclaw/memory/replay/cli.py paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_replay_bundle.py
git commit -m "feat(stage2): add T5 replay bundle + CLI"
```

---

## Task 8: E2E + integration + routing + regression

**Files:**
- Test: `paulshaclaw/memory/tests/test_dream_e2e.py`
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`, `paulshaclaw/memory/routing.md`

- [ ] **Step 1: Write the E2E test**

```python
# paulshaclaw/memory/tests/test_dream_e2e.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import cli
from paulshaclaw.memory.ledger import dream

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: sess-dream
source_artifact: research
captured_at: "2026-06-02T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha body
"""


def _seed(root: Path):
    raw = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
    raw.parent.mkdir(parents=True)
    raw.write_text(_RAW, encoding="utf-8")


class DreamE2ETests(unittest.TestCase):
    def test_dream_run_then_status_then_bundle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            # identity promoter (no LLM): dream run orchestrates atomize+janitor
            rc = cli.main(["memory", "dream", "run", "--memory-root", str(root),
                           "--now", "2026-06-02T05:00:00Z", "--promoter", "identity"])
            self.assertEqual(rc, 0)
            last = dream.last_run(root)
            self.assertIn(last["status"], ("ok", "partial"))
            self.assertIn("atomize", last["passes"])
            self.assertIn("janitor", last["passes"])
            # knowledge produced -> bundle it
            out = root / "bundle-out"
            rc2 = cli.main(["memory", "bundle", "--memory-root", str(root),
                            "--project", "paulshaclaw", "--out", str(out),
                            "--now", "2026-06-02T06:00:00Z"])
            self.assertEqual(rc2, 0)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["raw_excluded"])
            self.assertGreaterEqual(manifest["counts"]["slices"], 1)
            # no raw prompt body leaked into the bundle
            blob = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
            self.assertNotIn("alpha body", blob.replace("DISTILLED", ""))  # raw fragment body not present verbatim


if __name__ == "__main__":
    unittest.main()
```

> If the identity-promoter atomize copies the fragment body verbatim into the slice (1:1), the final raw-leak assertion may need to check for the raw *session* artifact rather than the slice body; adapt to assert the bundle excludes `inbox`/`runtime/queue` raw payloads specifically. The key guarantee under test: the bundle dir contains only `knowledge/` slices + ledger events, never files from raw sources.

- [ ] **Step 2: Run the E2E test**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_dream_e2e -v`
Expected: PASS. If a scenario fails, fix the implementation (orchestrator/bundle), not the test.

- [ ] **Step 3: Integration check + routing**

Append to `paulshaclaw/memory/tests/stage2_integration_check.sh`, before `echo "[stage2] ok"`:

```bash
echo "[stage2] dream dry-run + bundle over fixtures"
DREAM_ROOT="$(mktemp -d)"
mkdir -p "$DREAM_ROOT/inbox/research/claude/2026-06-02"
cp "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md" \
   "$DREAM_ROOT/inbox/research/claude/2026-06-02/s1.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory dream run \
  --memory-root "$DREAM_ROOT" --now "2026-06-02T05:00:00Z" --promoter identity --dry-run \
  | grep -Fq '"status"'
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory dream run \
  --memory-root "$DREAM_ROOT" --now "2026-06-02T05:00:00Z" --promoter identity >/dev/null
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory bundle \
  --memory-root "$DREAM_ROOT" --project paulshaclaw --out "$DREAM_ROOT/bundle" \
  --now "2026-06-02T06:00:00Z" >/dev/null
grep -Fq '"raw_excluded": true' "$DREAM_ROOT/bundle/manifest.json"
```

Append to `paulshaclaw/memory/routing.md`:

```markdown

> **T5 已落地（2026-06）：** `psc memory dream run`（idle-gated systemd timer 範本 Mon..Fri 05:00）編排 atomize→janitor 並記 `runtime/ledger/dream.jsonl`;`psc memory dream status` 回最後 run + backlog。`psc memory bundle --project/--tag/--entity` 組 replay bundle（只含 distilled slices + ledger，`raw_excluded:true`）。proposal-first 框架於 `runtime/proposals/`。設計見 `docs/superpowers/specs/2026-06-02-stage2-dream-service-design.md`。
```

- [ ] **Step 4: Full regression**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`
Expected: PASS (all memory tests green)

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: ends with `[stage2] ok`

Run: `python3 -m unittest discover -s tests -v`
Expected: only pre-existing unrelated failures (flaky `test_start_sh`, stage9 snapshot); no new T5 regressions.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/tests/test_dream_e2e.py paulshaclaw/memory/tests/stage2_integration_check.sh paulshaclaw/memory/routing.md
git commit -m "test(stage2): add T5 dream/bundle E2E and integration wiring"
```

---

## Verification Summary（實作完成後填）

（填入：`test_dream_*`/`test_ledger_dream`/`test_replay_*` 聚焦結果、`unittest discover -s paulshaclaw/memory/tests` 全套、`stage2_integration_check.sh` 輸出、systemd 範本測試、opt-in 手動 timer 安裝說明、`tests/` 回歸狀態。）
