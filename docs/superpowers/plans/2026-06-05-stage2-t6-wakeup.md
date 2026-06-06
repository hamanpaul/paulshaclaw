# Stage 2 T6 Wake-up + PreCompact Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the read/inject side of the memory system: a per-project wake-up brief (MOC primer + recent-K pointers) injected at session start via `additionalContext`, plus a PreCompact hook that snapshots the session into the importer before compaction loses detail.

**Architecture:** A CLI-agnostic `memory/wakeup/builder.py` produces the brief from existing data (T7 MOC file + lifecycle/retrieval_set ledgers). `memory/wakeup/cli.py` exposes `psc memory wakeup`. Four thin hooks (claude/copilot × session_start/precompact) call the builder or trigger the existing importer. PreCompact reuses the importer with a new `capture_scope="pre_compact"`. Fail-open everywhere; `now` is injected so the builder is deterministic.

**Tech Stack:** Python 3 stdlib, `unittest`. Reuse `importer/project_resolver`, `ledger/lifecycle` (`read_events`/`fold_lifecycle`), `ledger/retrieval_set` (`active_record_ids`), `moc/frontmatter_io`, T7 MOC output (`knowledge/<project>-moc.md`), and `importer.cli ingest`.

---

## File Structure

- Create: `paulshaclaw/memory/wakeup/__init__.py` — exports `build_brief`.
- Create: `paulshaclaw/memory/wakeup/builder.py` — `build_brief(...)` + helpers.
- Create: `paulshaclaw/memory/wakeup/cli.py` — `psc memory wakeup` handler (`run`).
- Modify: `paulshaclaw/memory/cli.py` — register `wakeup` subcommand.
- Modify: `paulshaclaw/memory/importer/pipeline.py:22` — add `"pre_compact": 0` to `_SCOPE_RANK`.
- Create: `paulshaclaw/memory/hooks/claude_session_start.py`, `copilot_session_start.py`.
- Create: `paulshaclaw/memory/hooks/claude_precompact.py`, `copilot_precompact.py`.
- Modify: `paulshaclaw/memory/hooks/install.sh` / `uninstall.sh` — wire SessionStart/PreCompact + sessionStart/preCompact.
- Create: `paulshaclaw/memory/wakeup/README.md`.
- Tests under `paulshaclaw/memory/tests/`: `test_wakeup_builder.py`, `test_wakeup_cli.py`, `test_session_start_hooks.py`, `test_precompact_hooks.py`, and extend `test_pipeline_idempotency.py` (or add `test_importer_scope_rank.py`).

**Existing symbols to reuse (do NOT re-implement):**
- `importer/project_resolver.py`: `resolve_project(*, cwd=None, git_toplevel=None, remote_url=None, config_path=None, memory_root=None) -> str` (returns slug or `"_unknown"`).
- `ledger/lifecycle.py`: `read_events(path) -> list`, `fold_lifecycle(events) -> {record_id: {last_state,last_event_ts,...}}`. **record_id == slice_id.**
- `ledger/retrieval_set.py`: `active_record_ids(lifecycle_path) -> set[str]`.
- `moc/frontmatter_io.py`: `read(text) -> (frontmatter: dict, body: str)`.
- MOC file: `knowledge/<project>-moc.md` (built by T7 `moc_builder.build_mocs`).
- `importer/cli.py`: `ingest --queue-item <path> --memory-root <root>`.
- Hook patterns: `hooks/copilot_session_end.py` (`_memory_root`, `_log_warn`, `_sanitize_id`, `_fire_importer`, atomic queue write), `hooks/claude_session_end.py`.

---

## Task 1: Add `pre_compact` scope rank

**Files:**
- Modify: `paulshaclaw/memory/importer/pipeline.py:22`
- Test: `paulshaclaw/memory/tests/test_importer_scope_rank.py`

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_importer_scope_rank.py`:

```python
import unittest
from paulshaclaw.memory.importer.pipeline import _SCOPE_RANK


class ScopeRankTest(unittest.TestCase):
    def test_pre_compact_is_turn_level(self):
        # pre_compact is a mid-session snapshot: same rank as a turn snapshot,
        # so a later session_end (rank 1) or watcher_final (rank 2) supersedes it.
        self.assertEqual(_SCOPE_RANK["pre_compact"], 0)
        self.assertGreater(_SCOPE_RANK["session_end"], _SCOPE_RANK["pre_compact"])
        self.assertGreater(_SCOPE_RANK["watcher_final"], _SCOPE_RANK["pre_compact"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_importer_scope_rank -v`
Expected: FAIL with `KeyError: 'pre_compact'`.

- [ ] **Step 3: Add the key**

In `paulshaclaw/memory/importer/pipeline.py` line 22, change:
```python
_SCOPE_RANK = {"turn": 0, "subagent": 0, "session_end": 1, "watcher_final": 2}
```
to:
```python
_SCOPE_RANK = {"turn": 0, "subagent": 0, "pre_compact": 0, "session_end": 1, "watcher_final": 2}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_importer_scope_rank -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/pipeline.py paulshaclaw/memory/tests/test_importer_scope_rank.py
git commit -m "feat(importer): add pre_compact capture scope rank"
```

---

## Task 2: Wake-up brief builder

**Files:**
- Create: `paulshaclaw/memory/wakeup/__init__.py`, `paulshaclaw/memory/wakeup/builder.py`
- Test: `paulshaclaw/memory/tests/test_wakeup_builder.py`

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_wakeup_builder.py`:

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.wakeup.builder import build_brief


def _write_slice(knowledge: Path, project: str, slice_id: str, title: str, body: str):
    d = knowledge / project
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{title}--{slice_id}.md"
    path.write_text(
        f"---\nslice_id: {slice_id}\nproject: {project}\nmemory_layer: knowledge\n"
        f"title: {title}\n---\n{body}\n",
        encoding="utf-8",
    )
    return path


def _created(ts: str, slice_id: str):
    # one lifecycle 'created' event line for a slice
    import json
    return json.dumps({
        "ts": ts, "event_id": f"{ts}-x", "record_id": slice_id, "event_type": "created",
        "source": "test", "reason": "r", "actor": "t", "run_id": None, "seq": 1,
        "metadata": None, "prev_hash": None, "event_hash": "h",
    })


class BuildBriefTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.knowledge = self.root / "knowledge"
        self.ledger = self.root / "runtime" / "ledger"
        self.ledger.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed(self):
        _write_slice(self.knowledge, "proj", "sl-1", "Older", "first line older\nmore")
        _write_slice(self.knowledge, "proj", "sl-2", "Newer", "first line newer\nmore")
        (self.knowledge / "proj-moc.md").write_text(
            "---\nmemory_layer: moc\n---\n# proj MOC\n\n- [[Newer--sl-2]]\n", encoding="utf-8"
        )
        (self.ledger / "lifecycle.jsonl").write_text(
            _created("2026-06-01T00:00:00Z", "sl-1") + "\n"
            + _created("2026-06-04T00:00:00Z", "sl-2") + "\n",
            encoding="utf-8",
        )

    def test_brief_has_map_and_recent_newest_first(self):
        self._seed()
        brief = build_brief(self.root, "proj", now="2026-06-05T00:00:00Z", k=8)
        self.assertIn("# Memory wake-up — proj", brief)
        self.assertIn("## Map", brief)
        self.assertIn("proj MOC", brief)             # MOC body included
        self.assertIn("## Recent", brief)
        # Newer (sl-2, 2026-06-04) must come before Older (sl-1, 2026-06-01)
        self.assertLess(brief.index("Newer--sl-2"), brief.index("Older--sl-1"))
        self.assertIn("first line newer", brief)     # one-line summary

    def test_unknown_project_returns_empty(self):
        self._seed()
        self.assertEqual(build_brief(self.root, "_unknown", now="2026-06-05T00:00:00Z"), "")

    def test_project_with_no_slices_returns_empty(self):
        self.assertEqual(build_brief(self.root, "ghost", now="2026-06-05T00:00:00Z"), "")

    def test_decayed_slice_excluded_from_recent(self):
        self._seed()
        import json
        with (self.ledger / "lifecycle.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": "2026-06-04T12:00:00Z", "event_id": "z", "record_id": "sl-2",
                "event_type": "decayed", "source": "t", "reason": "r", "actor": "t",
                "run_id": None, "seq": 2, "metadata": None, "prev_hash": "h", "event_hash": "h2",
            }) + "\n")
        brief = build_brief(self.root, "proj", now="2026-06-05T00:00:00Z")
        self.assertNotIn("Newer--sl-2", brief)       # decayed -> not active -> excluded

    def test_char_budget_truncates_map_tail_keeps_recent(self):
        self._seed()
        big = "X" * 5000
        (self.knowledge / "proj-moc.md").write_text(
            "---\nmemory_layer: moc\n---\n# proj MOC\n\n" + big + "\n", encoding="utf-8"
        )
        brief = build_brief(self.root, "proj", now="2026-06-05T00:00:00Z", char_budget=1500)
        self.assertLessEqual(len(brief), 1500)
        self.assertIn("## Recent", brief)            # Recent preserved
        self.assertIn("(truncated)", brief)

    def test_deterministic(self):
        self._seed()
        a = build_brief(self.root, "proj", now="2026-06-05T00:00:00Z")
        b = build_brief(self.root, "proj", now="2026-06-05T00:00:00Z")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_wakeup_builder -v`
Expected: FAIL (`ModuleNotFoundError: paulshaclaw.memory.wakeup.builder`).

- [ ] **Step 3: Implement `builder.py`**

Create `paulshaclaw/memory/wakeup/builder.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from paulshaclaw.memory.ledger import lifecycle
from paulshaclaw.memory.ledger import retrieval_set
from paulshaclaw.memory.moc.frontmatter_io import read as read_frontmatter

_SUMMARY_MAX = 120


def _lifecycle_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "lifecycle.jsonl"


def _first_nonempty_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def _scan_slices(knowledge: Path, project: str) -> dict[str, dict[str, Any]]:
    """Map slice_id -> {title, summary, stem} for knowledge slices of one project."""
    result: dict[str, dict[str, Any]] = {}
    if not knowledge.exists():
        return result
    for path in sorted(knowledge.rglob("*.md")):
        if path.is_symlink():
            continue
        try:
            fm, body = read_frontmatter(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fm.get("memory_layer") != "knowledge":
            continue
        if str(fm.get("project")) != project:
            continue
        slice_id = fm.get("slice_id")
        if not slice_id:
            continue
        title = str(fm.get("title") or path.stem)
        result[str(slice_id)] = {
            "title": title,
            "summary": _first_nonempty_line(body),
            "stem": path.stem,
        }
    return result


def _recent_lines(memory_root: Path, project: str, k: int) -> list[str]:
    lifecycle_path = _lifecycle_path(memory_root)
    events = lifecycle.read_events(lifecycle_path)
    if not events:
        return []
    folded = lifecycle.fold_lifecycle(events)
    active = retrieval_set.active_record_ids(lifecycle_path)
    slices = _scan_slices(memory_root / "knowledge", project)

    candidates = []
    for slice_id, meta in slices.items():
        if slice_id not in active:
            continue
        ts = (folded.get(slice_id) or {}).get("last_event_ts") or ""
        candidates.append((ts, slice_id, meta))
    # newest first; ISO8601 sorts lexically. Tie-break on slice_id for determinism.
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)

    lines = []
    for ts, _sid, meta in candidates[:k]:
        summary = meta["summary"][:_SUMMARY_MAX]
        lines.append(f"- [[{meta['stem']}]] — {summary} ({ts})")
    return lines


def _moc_body(memory_root: Path, project: str) -> str:
    moc_path = memory_root / "knowledge" / f"{project}-moc.md"
    if not moc_path.exists():
        return ""
    try:
        _fm, body = read_frontmatter(moc_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return body.strip()


def build_brief(
    memory_root: Path,
    project: str,
    *,
    now: str,
    k: int = 8,
    char_budget: int = 8000,
) -> str:
    """Build the wake-up brief for a project. Pure given inputs; empty when nothing to inject."""
    del now  # reserved for future recency windows; kept for deterministic signature
    memory_root = Path(memory_root)
    if not project or project == "_unknown":
        return ""

    recent = _recent_lines(memory_root, project, k)
    moc = _moc_body(memory_root, project)
    if not recent and not moc:
        return ""

    header = f"# Memory wake-up — {project}\n"
    recent_block = "\n## Recent\n" + ("\n".join(recent) if recent else "(none)") + "\n"

    # Budget: header + Recent are reserved first (continuity); Map fills the rest.
    reserved = len(header) + len(recent_block) + len("\n## Map\n")
    map_budget = max(0, char_budget - reserved)
    map_text = moc
    if len(map_text) > map_budget:
        marker = "\n…(truncated)"
        map_text = map_text[: max(0, map_budget - len(marker))].rstrip() + marker

    brief = f"{header}\n## Map\n{map_text}\n{recent_block}"
    if len(brief) > char_budget:
        brief = brief[:char_budget]
    return brief
```

Create `paulshaclaw/memory/wakeup/__init__.py`:
```python
from .builder import build_brief

__all__ = ["build_brief"]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_wakeup_builder -v`
Expected: PASS (all 6 cases).

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/wakeup/__init__.py paulshaclaw/memory/wakeup/builder.py paulshaclaw/memory/tests/test_wakeup_builder.py
git commit -m "feat(wakeup): per-project brief builder (MOC primer + recent-K)"
```

---

## Task 3: Wake-up CLI + `psc memory wakeup`

**Files:**
- Create: `paulshaclaw/memory/wakeup/cli.py`
- Modify: `paulshaclaw/memory/cli.py`
- Test: `paulshaclaw/memory/tests/test_wakeup_cli.py`

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_wakeup_cli.py`:

```python
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.wakeup import cli


def _seed(root: Path):
    k = root / "knowledge" / "proj"
    k.mkdir(parents=True, exist_ok=True)
    (k.parent / "proj-moc.md").write_text("---\nmemory_layer: moc\n---\n# proj MOC\n", encoding="utf-8")
    (k / "Title--sl-1.md").write_text(
        "---\nslice_id: sl-1\nproject: proj\nmemory_layer: knowledge\ntitle: Title\n---\nbody line\n",
        encoding="utf-8",
    )
    ledger = root / "runtime" / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    import json
    (ledger / "lifecycle.jsonl").write_text(json.dumps({
        "ts": "2026-06-04T00:00:00Z", "event_id": "a", "record_id": "sl-1", "event_type": "created",
        "source": "t", "reason": "r", "actor": "t", "run_id": None, "seq": 1,
        "metadata": None, "prev_hash": None, "event_hash": "h",
    }) + "\n", encoding="utf-8")


class WakeupCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(argv)
        return rc, buf.getvalue()

    def test_explicit_project_prints_brief(self):
        _seed(self.root)
        rc, out = self._run(["--project", "proj", "--memory-root", str(self.root)])
        self.assertEqual(rc, 0)
        self.assertIn("Memory wake-up — proj", out)

    def test_unknown_project_prints_nothing_rc0(self):
        _seed(self.root)
        rc, out = self._run(["--project", "_unknown", "--memory-root", str(self.root)])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_wakeup_cli -v`
Expected: FAIL (`ModuleNotFoundError` / no `main`).

- [ ] **Step 3: Implement `cli.py`**

Create `paulshaclaw/memory/wakeup/cli.py`:

```python
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from paulshaclaw.memory.importer.project_resolver import resolve_project
from .builder import build_brief


def _resolve(args: argparse.Namespace) -> str:
    if args.project:
        return args.project
    if args.cwd:
        return resolve_project(cwd=args.cwd, memory_root=args.memory_root)
    return "_unknown"


def run(args: argparse.Namespace) -> int:
    project = _resolve(args)
    now = args.now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    brief = build_brief(Path(args.memory_root), project, now=now, k=args.k, char_budget=args.char_budget)
    if brief:
        print(brief)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="psc memory wakeup")
    parser.add_argument("--memory-root", default=str(Path.home() / ".agents" / "memory"))
    parser.add_argument("--project", default=None)
    parser.add_argument("--cwd", default=None)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--char-budget", type=int, default=8000)
    parser.add_argument("--now", default=None)
    parser.set_defaults(func=run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register under `psc memory`**

In `paulshaclaw/memory/cli.py`, add a parser next to the other subcommands (mirror the `skillopt` block) and a handler. Add the parser block:
```python
    wakeup = memory_subparsers.add_parser("wakeup")
    wakeup.add_argument("--memory-root", default=str(Path.home() / ".agents" / "memory"))
    wakeup.add_argument("--project", default=None)
    wakeup.add_argument("--cwd", default=None)
    wakeup.add_argument("--k", type=int, default=8)
    wakeup.add_argument("--char-budget", type=int, default=8000)
    wakeup.add_argument("--now", default=None)
    wakeup.set_defaults(func=_wakeup)
```
And the handler (mirror `_skillopt`):
```python
def _wakeup(args: argparse.Namespace) -> int:
    from .wakeup import cli as wakeup_cli
    return wakeup_cli.run(args)
```

- [ ] **Step 5: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_wakeup_cli -v`
Expected: PASS.

Also smoke-test the registration: `python3 -m paulshaclaw.memory.cli memory wakeup --project _unknown --memory-root /tmp/nope` → prints nothing, rc 0.

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/wakeup/cli.py paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_wakeup_cli.py
git commit -m "feat(wakeup): psc memory wakeup CLI + subcommand"
```

---

## Task 4: Session-start hooks (Claude + Copilot)

**Files:**
- Create: `paulshaclaw/memory/hooks/claude_session_start.py`, `paulshaclaw/memory/hooks/copilot_session_start.py`
- Test: `paulshaclaw/memory/tests/test_session_start_hooks.py`

Both hooks: read stdin JSON → get `cwd` → `resolve_project` → `build_brief` → emit `additionalContext`. Fail-open: any error logs to `log/hooks.log` and exits 0 with no injection.

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_session_start_hooks.py`:

```python
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / "paulshaclaw" / "memory" / "hooks"


def _seed(root: Path, project: str):
    k = root / "knowledge" / project
    k.mkdir(parents=True, exist_ok=True)
    (k.parent / f"{project}-moc.md").write_text(
        f"---\nmemory_layer: moc\n---\n# {project} MOC\n", encoding="utf-8"
    )
    # projects.yaml so resolve_project maps cwd -> project
    cfg = root.parent / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "projects.yaml").write_text(
        f"projects:\n  - slug: {project}\n    roots:\n      - /work/{project}\n", encoding="utf-8"
    )


class SessionStartHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.mem = Path(self._tmp.name) / ".agents" / "memory"
        self.mem.mkdir(parents=True, exist_ok=True)
        _seed(self.mem, "proj")
        self.env = dict(os.environ)
        self.env["PSC_MEMORY_ROOT"] = str(self.mem)
        self.env["PYTHONPATH"] = str(REPO_ROOT)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, script, payload):
        proc = subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=json.dumps(payload), capture_output=True, text=True, env=self.env,
        )
        return proc

    def test_claude_session_start_emits_additional_context(self):
        proc = self._run("claude_session_start.py", {"cwd": "/work/proj", "session_id": "s1"})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertIn("additionalContext", out.get("hookSpecificOutput", out))
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", out.get("additionalContext", ""))
        self.assertIn("Memory wake-up — proj", ctx)

    def test_copilot_session_start_emits_additional_context(self):
        proc = self._run("copilot_session_start.py", {"cwd": "/work/proj", "sessionId": "s1"})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertIn("Memory wake-up — proj", out["additionalContext"])

    def test_unresolved_project_is_quiet_rc0(self):
        proc = self._run("copilot_session_start.py", {"cwd": "/elsewhere", "sessionId": "s1"})
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout or "{}")
        self.assertEqual(out.get("additionalContext", ""), "")

    def test_malformed_stdin_fails_open(self):
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "claude_session_start.py")],
            input="not json", capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_session_start_hooks -v`
Expected: FAIL (hook scripts do not exist).

- [ ] **Step 3: Implement a shared helper + the two hooks**

Create `paulshaclaw/memory/hooks/_wakeup_common.py`:
```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def memory_root() -> Path:
    env = os.environ.get("PSC_MEMORY_ROOT", "").strip()
    return Path(env) if env else Path.home() / ".agents" / "memory"


def log_warn(root: Path, tool: str, msg: str) -> None:
    try:
        log_path = root / "log" / "hooks.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"WARN {tool}: {msg}\n")
    except Exception:
        pass


def read_payload() -> dict:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def compute_brief(root: Path, cwd: str | None) -> str:
    """Resolve project from cwd and build the wake-up brief. Empty on any miss."""
    from paulshaclaw.memory.importer.project_resolver import resolve_project
    from paulshaclaw.memory.wakeup.builder import build_brief
    from datetime import datetime, timezone

    project = resolve_project(cwd=cwd, memory_root=str(root)) if cwd else "_unknown"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return build_brief(root, project, now=now)
```

Create `paulshaclaw/memory/hooks/claude_session_start.py`:
```python
#!/usr/bin/env python3
"""Claude Code SessionStart hook: inject a per-project memory wake-up brief."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wakeup_common import compute_brief, log_warn, memory_root, read_payload  # noqa: E402

TOOL = "claude-session-start"


def main() -> int:
    root = memory_root()
    try:
        payload = read_payload()
        brief = compute_brief(root, payload.get("cwd"))
    except Exception as exc:  # fail-open
        log_warn(root, TOOL, str(exc))
        brief = ""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": brief,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `paulshaclaw/memory/hooks/copilot_session_start.py`:
```python
#!/usr/bin/env python3
"""GitHub Copilot CLI sessionStart hook: inject a per-project memory wake-up brief."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wakeup_common import compute_brief, log_warn, memory_root, read_payload  # noqa: E402

TOOL = "copilot-session-start"


def main() -> int:
    root = memory_root()
    try:
        payload = read_payload()
        brief = compute_brief(root, payload.get("cwd"))
    except Exception as exc:  # fail-open
        log_warn(root, TOOL, str(exc))
        brief = ""
    print(json.dumps({"additionalContext": brief}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_session_start_hooks -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/_wakeup_common.py paulshaclaw/memory/hooks/claude_session_start.py paulshaclaw/memory/hooks/copilot_session_start.py paulshaclaw/memory/tests/test_session_start_hooks.py
git commit -m "feat(hooks): session-start wake-up injection for claude/copilot"
```

---

## Task 5: PreCompact hooks (Claude + Copilot)

**Files:**
- Create: `paulshaclaw/memory/hooks/claude_precompact.py`, `paulshaclaw/memory/hooks/copilot_precompact.py`
- Test: `paulshaclaw/memory/tests/test_precompact_hooks.py`

Both hooks mirror the existing `*_session_end.py` capture flow but set `capture_scope="pre_compact"`: write an atomic queue payload to `runtime/queue/<tool>__<sid>.json` and fire-and-forget trigger the importer. Fail-open; never block compaction.

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_precompact_hooks.py`:

```python
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / "paulshaclaw" / "memory" / "hooks"


class PrecompactHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.mem = Path(self._tmp.name) / ".agents" / "memory"
        self.mem.mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ)
        self.env["PSC_MEMORY_ROOT"] = str(self.mem)
        self.env["PYTHONPATH"] = str(REPO_ROOT)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, script, payload):
        return subprocess.run(
            [sys.executable, str(HOOKS / script)],
            input=json.dumps(payload), capture_output=True, text=True, env=self.env,
        )

    def _queue_files(self):
        q = self.mem / "runtime" / "queue"
        return sorted(p for p in q.glob("*.json")) if q.exists() else []

    def test_copilot_precompact_writes_pre_compact_payload(self):
        proc = self._run("copilot_precompact.py", {"sessionId": "s9", "cwd": "/w"})
        self.assertEqual(proc.returncode, 0)
        files = self._queue_files()
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["capture_scope"], "pre_compact")
        self.assertEqual(payload["session_id"], "s9")

    def test_claude_precompact_writes_pre_compact_payload(self):
        proc = self._run("claude_precompact.py", {"session_id": "s8", "cwd": "/w", "transcript_path": "/tmp/t.jsonl"})
        self.assertEqual(proc.returncode, 0)
        files = self._queue_files()
        self.assertEqual(len(files), 1)
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["capture_scope"], "pre_compact")

    def test_malformed_stdin_fails_open_no_queue(self):
        proc = subprocess.run(
            [sys.executable, str(HOOKS / "claude_precompact.py")],
            input="not json", capture_output=True, text=True, env=self.env,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(self._queue_files(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_precompact_hooks -v`
Expected: FAIL (hook scripts do not exist).

- [ ] **Step 3: Implement the two hooks**

Add to `paulshaclaw/memory/hooks/_wakeup_common.py`:
```python
def sanitize_id(value: str) -> str:
    import re
    return re.sub(r"[/\\:]+", "__", value)


def write_queue_payload(root: Path, tool: str, payload: dict) -> Path:
    """Atomically write a queue payload tagged capture_scope=pre_compact."""
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "unknown")
    queue_payload = dict(payload)
    queue_payload["tool"] = tool
    queue_payload["session_id"] = session_id
    queue_payload.pop("sessionId", None)
    queue_payload["capture_scope"] = "pre_compact"

    queue_dir = root / "runtime" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{tool}__{sanitize_id(session_id)}.json"
    queue_path = queue_dir / filename
    tmp_path = queue_dir / f".{filename}.tmp"
    tmp_path.write_text(json.dumps(queue_payload, sort_keys=True, indent=2), encoding="utf-8")
    tmp_path.replace(queue_path)
    return queue_path


def fire_importer(root: Path, tool: str, queue_path: Path) -> None:
    import subprocess
    venv_python = root / "hooks" / ".venv" / "bin" / "python"
    interp = str(venv_python) if venv_python.exists() else sys.executable
    try:
        subprocess.Popen(
            [interp, "-m", "paulshaclaw.memory.importer.cli", "ingest",
             "--queue-item", str(queue_path), "--memory-root", str(root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except Exception as exc:
        log_warn(root, tool, f"importer trigger failed: {exc}")
```

Create `paulshaclaw/memory/hooks/copilot_precompact.py`:
```python
#!/usr/bin/env python3
"""GitHub Copilot CLI preCompact hook: snapshot the session before compaction."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wakeup_common import fire_importer, log_warn, memory_root, read_payload, write_queue_payload  # noqa: E402

TOOL = "copilot-cli"


def main() -> int:
    root = memory_root()
    try:
        payload = read_payload()
        queue_path = write_queue_payload(root, TOOL, payload)
        fire_importer(root, TOOL, queue_path)
    except Exception as exc:  # fail-open: never block compaction
        log_warn(root, "copilot-precompact", str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `paulshaclaw/memory/hooks/claude_precompact.py` (identical except `TOOL = "claude"` and the log tag):
```python
#!/usr/bin/env python3
"""Claude Code PreCompact hook: snapshot the session before compaction."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _wakeup_common import fire_importer, log_warn, memory_root, read_payload, write_queue_payload  # noqa: E402

TOOL = "claude"


def main() -> int:
    root = memory_root()
    try:
        payload = read_payload()
        queue_path = write_queue_payload(root, TOOL, payload)
        fire_importer(root, TOOL, queue_path)
    except Exception as exc:  # fail-open: never block compaction
        log_warn(root, "claude-precompact", str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_precompact_hooks -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/_wakeup_common.py paulshaclaw/memory/hooks/claude_precompact.py paulshaclaw/memory/hooks/copilot_precompact.py paulshaclaw/memory/tests/test_precompact_hooks.py
git commit -m "feat(hooks): precompact session snapshot for claude/copilot"
```

---

## Task 6: Wire install.sh / uninstall.sh

**Files:**
- Modify: `paulshaclaw/memory/hooks/install.sh`, `paulshaclaw/memory/hooks/uninstall.sh`

- [ ] **Step 1: Copy the new hook scripts on install**

In `install.sh`, find the loop that copies hook scripts (the `for script in install.sh uninstall.sh claude_session_end.py codex_session_end.py copilot_session_end.py; do` list) and add the five new files: `_wakeup_common.py claude_session_start.py copilot_session_start.py claude_precompact.py copilot_precompact.py`.

- [ ] **Step 2: Register Claude SessionStart + PreCompact**

In the Claude `settings.json` merge section (mirror the existing `SessionEnd` block), add two more managed entries: one under `hooks.SessionStart` running `…/hooks/claude_session_start.py`, one under `hooks.PreCompact` running `…/hooks/claude_precompact.py`. Reuse the existing venv-python command prefix and managed-marker matching so re-runs are idempotent.

- [ ] **Step 3: Register Copilot sessionStart + preCompact**

In the Copilot `paulsha-memory.json` writer (Step 6 section), extend the JSON so `hooks` contains `sessionStart` and `preCompact` arrays (alongside the existing `sessionEnd`), each with a `{"type": "command", "command": "<venv-python> <hook_dir>/<script>"}` entry.

- [ ] **Step 4: Mirror removals in uninstall.sh**

In `uninstall.sh`, remove the SessionStart/PreCompact managed entries from Claude settings and the sessionStart/preCompact arrays from the Copilot config, mirroring how SessionEnd/sessionEnd are removed.

- [ ] **Step 5: Verify install is idempotent (dry sanity)**

Run on a throwaway config root:
```bash
PSC_CONFIG_ROOT=/tmp/psc-t6 bash paulshaclaw/memory/hooks/install.sh --config-root /tmp/psc-t6 || true
python3 -c "import json;print(json.load(open('/tmp/psc-t6/.copilot/hooks/paulsha-memory.json'))['hooks'].keys())"
```
Expected: includes `sessionStart`, `preCompact`, `sessionEnd`. Re-running install must not duplicate entries.

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/hooks/install.sh paulshaclaw/memory/hooks/uninstall.sh
git commit -m "feat(hooks): install/uninstall wiring for session-start + precompact"
```

---

## Task 7: README, full suite, policy gate, archive

**Files:**
- Create: `paulshaclaw/memory/wakeup/README.md`

- [ ] **Step 1: Write `README.md`**

Document: wake-up injects a per-project brief (MOC primer + recent-K pointers) at session start via `additionalContext` (Claude `SessionStart`, Copilot `sessionStart`, Codex via Claude's hook); PreCompact snapshots the session into the importer (`capture_scope=pre_compact`) before compaction; everything is fail-open and never blocks session start or compaction; the builder is deterministic (`now` injected) and read-only (no ledger writes); reuses `project_resolver`, `lifecycle`/`retrieval_set`, T7 MOC, and the importer.

- [ ] **Step 2: Run the full memory suite**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests`
Expected: all PASS (including the 5 new test modules).

- [ ] **Step 3: Run the repo policy / lint gate**

Run the repo policy check + frontmatter/policy-consumer lint exactly as prior Stage 2 changes do. Expected: green. Branch `feature/stage2-t6-wakeup` satisfies R-12 (no dots).

- [ ] **Step 4: Commit docs**

```bash
git add paulshaclaw/memory/wakeup/README.md
git commit -m "docs(wakeup): module README (inject, precompact, fail-open)"
```

- [ ] **Step 5: openspec-archive after merge**

After the PR merges, archive the `stage2-t6-wakeup` OpenSpec change into `openspec/changes/archive/` and sync its spec delta into `openspec/specs/stage2-memory-governance/spec.md`, mirroring the most recent archived Stage 2 change.

---

## Self-Review notes (for the implementer)
- Determinism: never call wall-clock inside `builder.py`; `now` enters only at the CLI/hook boundary. Recent ordering keys off `last_event_ts` (ISO8601 lexical sort) with `slice_id` tie-break.
- Zero duplication: project from `project_resolver`; recency from `lifecycle`+`retrieval_set`; map from the T7 MOC file; capture from the importer. The builder never writes.
- Fail-open: session-start hooks always print valid JSON and exit 0; precompact hooks never raise to the CLI and never block compaction.
- `record_id == slice_id` — `fold_lifecycle` keys and `active_record_ids` are slice ids, matching the knowledge-slice `slice_id` frontmatter.
- Budget: Recent block is reserved before Map; only the Map tail is truncated, with a `…(truncated)` marker, and the final brief is hard-capped at `char_budget`.
