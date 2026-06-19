# Stage 2 Topic 3 — Atomizer / Linker (deterministic MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `atomizer` that promotes `inbox` raw sessions into Stage-3-conformant `knowledge` slices via two re-entrant passes (structural split → 1:1 promote), plus `processing`/`relations` ledgers, with flow-through archival.

**Architecture:** Pure logic (`splitter`, `slice_frontmatter`, `promoter`) is separated from IO/orchestration (`pipeline`, `ledger/*`). Ledgers are append-only JSONL + flock. The pipeline runs `split_pass` then `promote_pass`; each derives its work-list from filesystem + processing ledger, so it is idempotent and crash-resumable. No LLM, no randomness, injected `now`.

**Tech Stack:** Python 3.12, stdlib (`fcntl`/`json`/`hashlib`/`re`/`dataclasses`), PyYAML (via try/except), `unittest`. Cross-stage contract: `paulshaclaw.lifecycle.schema`.

**Design:** `docs/superpowers/specs/2026-05-31-stage2-t3-atomizer-linker-design.md`
**OpenSpec:** `openspec/changes/stage2-t3-atomizer-linker/`

**Shared conventions (reuse existing code):**
- canonical json: `json.dumps(v, sort_keys=True, separators=(",", ":"))`
- flock: open data file `a+`/`r`, `fcntl.flock(LOCK_EX|LOCK_SH)` (mirror `ledger/lifecycle.py`)
- yaml read: try `import yaml; yaml.safe_load` else JSON (mirror `policy/loader.py`)
- hash: `hashlib.sha256(canonical.encode()).hexdigest()`
- Stage 3 schema API: `paulshaclaw.lifecycle.schema.{validate_frontmatter, compute_checksum, ARTIFACT_KINDS, PHASES}`

**Canonical data shapes (keep consistent across tasks):**
- `Fragment(project, source_agent, source_session, source_artifact, captured_at, provenance: dict, fragment_index: int, body: str)`
- `Slice(slice_id: str, frontmatter: dict, body: str)`
- processing event: `{"ts","session_key","state","atomizer_config_hash", ...extra}`; states `split`/`promoted`
- relation edge: `{"ts","type","from","to","atomizer_config_hash"}`; types `fragment_of`/`promoted_to`/`distilled_from`/`supersedes`
- `slice_id = "sl-" + sha256("<project>|<agent>|<session>|<index>")[:16]`

---

## Task 1: `ledger/processing.py` — session state machine

**Files:**
- Create: `paulshaclaw/memory/ledger/processing.py`
- Test: `paulshaclaw/memory/tests/test_ledger_processing.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_ledger_processing.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import processing


class ProcessingLedgerTests(unittest.TestCase):
    def test_append_then_fold_latest_state(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processing.append_state(root, session_key="claude:s1", state="split",
                                    now="2026-05-31T01:00:00Z", config_hash="h", fragments=2)
            processing.append_state(root, session_key="claude:s1", state="promoted",
                                    now="2026-05-31T02:00:00Z", config_hash="h", slices=2)
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")

    def test_no_entry_means_not_processed(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(processing.state_of(Path(tmp), "claude:s1"))

    def test_split_state_is_in_process(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processing.append_state(root, session_key="claude:s1", state="split",
                                    now="2026-05-31T01:00:00Z", config_hash="h", fragments=1)
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")

    def test_ts_uses_injected_now(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            processing.append_state(root, session_key="claude:s1", state="split",
                                    now="2099-01-01T00:00:00Z", config_hash="h", fragments=1)
            self.assertEqual(processing.read_events(root)[0]["ts"], "2099-01-01T00:00:00Z")

    def test_corrupt_line_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = processing.processing_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok":1}\nbroken\n', encoding="utf-8")
            with self.assertRaises(processing.ProcessingLedgerError):
                processing.read_events(root)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_processing -v`
Expected: FAIL with `ImportError: cannot import name 'processing'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/processing.py
from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

VALID_STATES = {"split", "promoted"}


class ProcessingLedgerError(Exception):
    """Raised when the processing ledger cannot be safely read."""


def processing_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "processing.jsonl"


def append_state(memory_root: Path, *, session_key: str, state: str, now: str,
                 config_hash: str, **extra: Any) -> None:
    if state not in VALID_STATES:
        raise ValueError(f"invalid processing state: {state}")
    path = processing_path(memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": now, "session_key": session_key, "state": state,
             "atomizer_config_hash": config_hash, **extra}
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_events(memory_root: Path) -> list[dict[str, Any]]:
    path = processing_path(memory_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for lineno, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    events.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise ProcessingLedgerError(
                        f"corrupt processing ledger at line {lineno}: {exc}") from exc
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return events


def fold_states(memory_root: Path) -> dict[str, str]:
    indexed = sorted(enumerate(read_events(memory_root)),
                     key=lambda pair: (pair[1].get("ts", ""), pair[0]))
    state: dict[str, str] = {}
    for _, event in indexed:
        key = event.get("session_key")
        if key is not None:
            state[key] = event.get("state", "")
    return state


def state_of(memory_root: Path, session_key: str) -> str | None:
    return fold_states(memory_root).get(session_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_processing -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/processing.py paulshaclaw/memory/tests/test_ledger_processing.py
git commit -m "feat(stage2): add T3 processing ledger"
```

---

## Task 2: `ledger/relations.py` — derivation graph

**Files:**
- Create: `paulshaclaw/memory/ledger/relations.py`
- Test: `paulshaclaw/memory/tests/test_ledger_relations.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_ledger_relations.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import relations


class RelationsLedgerTests(unittest.TestCase):
    def test_append_and_neighbors(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            relations.append_edge(root, type="distilled_from", frm="slice:sl-1",
                                  to="session:claude:s1", now="2026-05-31T01:00:00Z", config_hash="h")
            got = relations.neighbors(root, "session:claude:s1")
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["type"], "distilled_from")
            self.assertEqual(got[0]["from"], "slice:sl-1")

    def test_neighbors_matches_from_or_to(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            relations.append_edge(root, type="fragment_of", frm="fragment:f0",
                                  to="session:claude:s1", now="t1", config_hash="h")
            self.assertEqual(len(relations.neighbors(root, "fragment:f0")), 1)
            self.assertEqual(len(relations.neighbors(root, "session:claude:s1")), 1)

    def test_neighbors_dedups_identical_edges(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for _ in range(2):
                relations.append_edge(root, type="fragment_of", frm="fragment:f0",
                                      to="session:claude:s1", now="t1", config_hash="h")
            self.assertEqual(len(relations.neighbors(root, "fragment:f0")), 1)

    def test_ts_uses_injected_now(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            relations.append_edge(root, type="fragment_of", frm="a", to="b",
                                  now="2099-01-01T00:00:00Z", config_hash="h")
            self.assertEqual(relations.read_edges(root)[0]["ts"], "2099-01-01T00:00:00Z")

    def test_corrupt_line_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = relations.relations_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok":1}\nbroken\n', encoding="utf-8")
            with self.assertRaises(relations.RelationsLedgerError):
                relations.read_edges(root)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_relations -v`
Expected: FAIL with `ImportError: cannot import name 'relations'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/relations.py
from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

VALID_EDGE_TYPES = {"fragment_of", "promoted_to", "distilled_from", "supersedes"}


class RelationsLedgerError(Exception):
    """Raised when the relations ledger cannot be safely read."""


def relations_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "relations.jsonl"


def append_edge(memory_root: Path, *, type: str, frm: str, to: str, now: str,
                config_hash: str) -> None:
    if type not in VALID_EDGE_TYPES:
        raise ValueError(f"invalid relation type: {type}")
    path = relations_path(memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    edge = {"ts": now, "type": type, "from": frm, "to": to,
            "atomizer_config_hash": config_hash}
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(edge, sort_keys=True, separators=(",", ":")) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_edges(memory_root: Path) -> list[dict[str, Any]]:
    path = relations_path(memory_root)
    if not path.exists():
        return []
    edges: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            for lineno, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    edges.append(json.loads(stripped))
                except json.JSONDecodeError as exc:
                    raise RelationsLedgerError(
                        f"corrupt relations ledger at line {lineno}: {exc}") from exc
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return edges


def neighbors(memory_root: Path, node: str) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for edge in read_edges(memory_root):
        if edge.get("from") != node and edge.get("to") != node:
            continue
        key = (edge.get("type", ""), edge.get("from", ""), edge.get("to", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(edge)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_ledger_relations -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/relations.py paulshaclaw/memory/tests/test_ledger_relations.py
git commit -m "feat(stage2): add T3 relations ledger"
```

---

## Task 3: `atomizer/config.py` + `atomizer.yaml`

**Files:**
- Create: `paulshaclaw/memory/atomizer/__init__.py`
- Create: `paulshaclaw/memory/atomizer/atomizer.yaml`
- Create: `paulshaclaw/memory/atomizer/config.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_config.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_config.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import config as atomizer_config


class AtomizerConfigTests(unittest.TestCase):
    def test_load_defaults(self):
        cfg, h = atomizer_config.load_config(override_path=None)
        self.assertEqual(cfg.default_artifact_kind, "report")
        self.assertEqual(cfg.default_phase, "review")
        self.assertGreater(cfg.max_fragment_chars, 0)
        self.assertTrue(cfg.boundary_patterns)
        self.assertEqual(len(h), 64)

    def test_override_merges_and_changes_hash(self):
        _, base = atomizer_config.load_config(override_path=None)
        with TemporaryDirectory() as tmp:
            ov = Path(tmp) / "atomizer.override.yaml"
            ov.write_text("split:\n  max_fragment_chars: 100\n", encoding="utf-8")
            cfg, h = atomizer_config.load_config(override_path=ov)
            self.assertEqual(cfg.max_fragment_chars, 100)
            self.assertEqual(cfg.default_artifact_kind, "report")  # default preserved
            self.assertNotEqual(h, base)

    def test_unsupported_schema_fails_closed(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "atomizer.yaml").write_text("schema_version: 9\n", encoding="utf-8")
            with self.assertRaises(atomizer_config.AtomizerConfigError):
                atomizer_config.load_config(default_dir=d, override_path=None)

    def test_hash_deterministic(self):
        _, h1 = atomizer_config.load_config(override_path=None)
        _, h2 = atomizer_config.load_config(override_path=None)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_config -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.atomizer'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/__init__.py
```

```yaml
# paulshaclaw/memory/atomizer/atomizer.yaml
schema_version: 1
split:
  boundary_patterns:
    - '^#{1,6}\s'
  max_fragment_chars: 8000
artifact_kind_map:
  research: research
  plan: plan
  plans: plan
  spec: spec
  report: report
  reports: report
  review: review
  session: report
  sessions: report
phase_map:
  research: research
  spec: define
  plan: plan
  report: review
  review: review
default_artifact_kind: report
default_phase: review
```

```python
# paulshaclaw/memory/atomizer/config.py
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent
_SUPPORTED_SCHEMA = "1"
_DEFAULT_SENTINEL = object()


class AtomizerConfigError(Exception):
    """Raised on invalid or unsupported atomizer config (fail-closed)."""


@dataclass(frozen=True)
class AtomizerConfig:
    schema_version: str
    boundary_patterns: tuple[str, ...]
    max_fragment_chars: int
    artifact_kind_map: dict[str, str] = field(default_factory=dict)
    phase_map: dict[str, str] = field(default_factory=dict)
    default_artifact_kind: str = "report"
    default_phase: str = "review"


def _read_mapping(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise AtomizerConfigError(f"atomizer config must be a mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_override(override_path: str | Path | None | object) -> Path | None:
    if override_path is _DEFAULT_SENTINEL:
        return Path.home() / ".config" / "paulshaclaw" / "atomizer.override.yaml"
    if override_path is None:
        return None
    return Path(override_path)


def load_config(default_dir: str | Path | None = None,
                override_path: str | Path | None | object = _DEFAULT_SENTINEL
                ) -> tuple[AtomizerConfig, str]:
    config_dir = Path(default_dir) if default_dir is not None else DEFAULT_CONFIG_DIR
    effective = dict(_read_mapping(config_dir / "atomizer.yaml"))

    ov = _resolve_override(override_path)
    if ov is not None and ov.exists():
        effective = _deep_merge(effective, _read_mapping(ov))

    if str(effective.get("schema_version", "")) != _SUPPORTED_SCHEMA:
        raise AtomizerConfigError(
            f"unsupported atomizer schema_version: {effective.get('schema_version')}")

    split = effective.get("split", {})
    config = AtomizerConfig(
        schema_version=_SUPPORTED_SCHEMA,
        boundary_patterns=tuple(str(p) for p in split.get("boundary_patterns", [])),
        max_fragment_chars=int(split.get("max_fragment_chars", 8000)),
        artifact_kind_map={str(k): str(v) for k, v in (effective.get("artifact_kind_map") or {}).items()},
        phase_map={str(k): str(v) for k, v in (effective.get("phase_map") or {}).items()},
        default_artifact_kind=str(effective.get("default_artifact_kind", "report")),
        default_phase=str(effective.get("default_phase", "review")),
    )
    config_hash = hashlib.sha256(
        json.dumps(effective, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return config, config_hash
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_config -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/__init__.py paulshaclaw/memory/atomizer/atomizer.yaml paulshaclaw/memory/atomizer/config.py paulshaclaw/memory/tests/test_atomizer_config.py
git commit -m "feat(stage2): add T3 atomizer config loader"
```

---

## Task 4: `atomizer/splitter.py` — deterministic structural splitter

**Files:**
- Create: `paulshaclaw/memory/atomizer/splitter.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_splitter.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_splitter.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import splitter
from paulshaclaw.memory.atomizer.config import AtomizerConfig

CFG = AtomizerConfig(schema_version="1", boundary_patterns=(r"^#{1,6}\s",),
                     max_fragment_chars=8000, artifact_kind_map={}, phase_map={},
                     default_artifact_kind="report", default_phase="review")


class SplitterTests(unittest.TestCase):
    def test_splits_on_heading_boundary(self):
        body = "# A\nalpha\n# B\nbeta\n"
        frags = splitter.split(body, CFG)
        self.assertEqual(len(frags), 2)
        self.assertIn("alpha", frags[0])
        self.assertIn("beta", frags[1])

    def test_empty_body_yields_zero_fragments(self):
        self.assertEqual(splitter.split("", CFG), [])
        self.assertEqual(splitter.split("   \n\n  ", CFG), [])

    def test_no_boundary_returns_single_fragment(self):
        frags = splitter.split("just text\nmore text\n", CFG)
        self.assertEqual(len(frags), 1)
        self.assertIn("just text", frags[0])

    def test_oversize_fragment_is_split_by_max_chars(self):
        cfg = AtomizerConfig(schema_version="1", boundary_patterns=(r"^#{1,6}\s",),
                             max_fragment_chars=10, artifact_kind_map={}, phase_map={},
                             default_artifact_kind="report", default_phase="review")
        body = "# H\n" + ("x" * 35) + "\n"
        frags = splitter.split(body, cfg)
        self.assertTrue(all(len(f) <= 10 for f in frags))
        self.assertGreater(len(frags), 1)

    def test_deterministic(self):
        body = "# A\nalpha\n# B\nbeta\n"
        self.assertEqual(splitter.split(body, CFG), splitter.split(body, CFG))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_splitter -v`
Expected: FAIL with `ImportError: cannot import name 'splitter'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/splitter.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import AtomizerConfig


@dataclass(frozen=True)
class Fragment:
    project: str
    source_agent: str
    source_session: str
    source_artifact: str
    captured_at: str
    provenance: dict[str, str]
    fragment_index: int
    body: str


def split(body: str, config: AtomizerConfig) -> list[str]:
    """Deterministically segment a session body into fragment texts."""
    patterns = [re.compile(p) for p in config.boundary_patterns]
    lines = body.splitlines()

    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        is_boundary = any(p.search(line) for p in patterns)
        if is_boundary and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)

    fragments: list[str] = []
    for group in groups:
        text = "\n".join(group).strip()
        if not text:
            continue
        fragments.extend(_enforce_max_chars(text, config.max_fragment_chars))
    return fragments


def _enforce_max_chars(text: str, limit: int) -> list[str]:
    if limit <= 0 or len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip("\n")
    if remaining.strip():
        chunks.append(remaining.strip())
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_splitter -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/splitter.py paulshaclaw/memory/tests/test_atomizer_splitter.py
git commit -m "feat(stage2): add T3 deterministic splitter"
```

---

## Task 5: `atomizer/slice_frontmatter.py` — union frontmatter + dual validation

**Files:**
- Create: `paulshaclaw/memory/atomizer/slice_frontmatter.py`
- Test: `paulshaclaw/memory/tests/test_slice_frontmatter.py`

**Note:** The serialized slice must parse under BOTH Stage 3's flat parser (`lifecycle.schema.parse_artifact_text`, for `lifecycle.gate`) AND T4's YAML reader (nested `provenance`). Nested provenance lines parse as flat `key: value` under Stage 3 (provenance is not Stage-3-required, so it is tolerated) and as a nested dict under T4's `yaml.safe_load`.

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_slice_frontmatter.py
from __future__ import annotations

import unittest

from paulshaclaw.lifecycle.schema import compute_checksum, parse_artifact_text, validate_frontmatter
from paulshaclaw.memory.atomizer import slice_frontmatter
from paulshaclaw.memory.atomizer.config import AtomizerConfig
from paulshaclaw.memory.atomizer.splitter import Fragment

CFG = AtomizerConfig(
    schema_version="1", boundary_patterns=(r"^#{1,6}\s",), max_fragment_chars=8000,
    artifact_kind_map={"research": "research", "session": "report"},
    phase_map={"research": "research", "report": "review"},
    default_artifact_kind="report", default_phase="review")


def _frag(source_artifact="research", index=0, body="alpha"):
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact=source_artifact, captured_at="2026-05-31T00:00:00Z",
                    provenance={"repo": "paulshaclaw", "commit": "c", "path": "docs/x.md"},
                    fragment_index=index, body=body)


class SliceFrontmatterTests(unittest.TestCase):
    def test_slice_id_deterministic(self):
        a = slice_frontmatter.build(_frag(), CFG)
        b = slice_frontmatter.build(_frag(), CFG)
        self.assertEqual(a.slice_id, b.slice_id)
        self.assertTrue(a.slice_id.startswith("sl-"))

    def test_slice_id_varies_by_fragment_index(self):
        self.assertNotEqual(slice_frontmatter.build(_frag(index=0), CFG).slice_id,
                            slice_frontmatter.build(_frag(index=1), CFG).slice_id)

    def test_artifact_kind_and_phase_mapping(self):
        s = slice_frontmatter.build(_frag(source_artifact="research"), CFG)
        self.assertEqual(s.frontmatter["artifact_kind"], "research")
        self.assertEqual(s.frontmatter["phase"], "research")

    def test_unknown_artifact_uses_defaults(self):
        s = slice_frontmatter.build(_frag(source_artifact="mystery"), CFG)
        self.assertEqual(s.frontmatter["artifact_kind"], "report")
        self.assertEqual(s.frontmatter["phase"], "review")

    def test_has_t4_contract_fields(self):
        fm = slice_frontmatter.build(_frag(), CFG).frontmatter
        for key in ("memory_layer", "source_agent", "captured_at", "provenance", "supersedes"):
            self.assertIn(key, fm)
        self.assertEqual(fm["memory_layer"], "knowledge")

    def test_checksum_matches_body(self):
        s = slice_frontmatter.build(_frag(body="hello body"), CFG)
        self.assertEqual(s.frontmatter["checksum"], compute_checksum(s.body))

    def test_passes_stage3_validation(self):
        s = slice_frontmatter.build(_frag(), CFG)
        result = validate_frontmatter(frontmatter=s.frontmatter, body=s.body)
        self.assertTrue(result.ok, result.errors)

    def test_serialized_slice_parses_and_validates(self):
        s = slice_frontmatter.build(_frag(), CFG)
        text = slice_frontmatter.render(s)
        doc = parse_artifact_text(text)
        result = validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body)
        self.assertTrue(result.ok, result.errors)

    def test_validate_reports_t4_gap(self):
        fm = {"phase": "research"}  # missing everything
        errors = slice_frontmatter.validate(fm, "body")
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_slice_frontmatter -v`
Expected: FAIL with `ImportError: cannot import name 'slice_frontmatter'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/slice_frontmatter.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from paulshaclaw.lifecycle import schema as stage3
from .config import AtomizerConfig
from .splitter import Fragment

_T4_FIELDS = ("memory_layer", "source_agent", "captured_at", "provenance", "supersedes")
# Stage 3 ordered fields first, then T4 + provenance handled specially in render().
_SCALAR_ORDER = (
    "phase", "project", "slice_id", "artifact_kind", "version", "created_at",
    "created_by", "source_session", "gate_required", "checksum",
    "memory_layer", "source_agent", "captured_at", "supersedes",
    "distilled_from", "fragment_ref",
)


@dataclass(frozen=True)
class Slice:
    slice_id: str
    frontmatter: dict[str, object]
    body: str


def _slice_id(fragment: Fragment) -> str:
    key = f"{fragment.project}|{fragment.source_agent}|{fragment.source_session}|{fragment.fragment_index}"
    return "sl-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def build(fragment: Fragment, config: AtomizerConfig) -> Slice:
    body = fragment.body
    artifact_kind = config.artifact_kind_map.get(fragment.source_artifact, config.default_artifact_kind)
    phase = config.phase_map.get(artifact_kind, config.default_phase)
    slice_id = _slice_id(fragment)
    session_ref = f"{fragment.source_agent}:{fragment.source_session}"
    fragment_ref = f"{fragment.source_agent}__{fragment.source_session}__{fragment.fragment_index:03d}"
    frontmatter: dict[str, object] = {
        # Stage 3 required
        "phase": phase,
        "project": fragment.project,
        "slice_id": slice_id,
        "artifact_kind": artifact_kind,
        "version": "1",
        "created_at": fragment.captured_at,
        "created_by": fragment.source_agent,
        "source_session": fragment.source_session,
        "gate_required": False,
        "checksum": stage3.compute_checksum(body),
        # T4 read contract
        "memory_layer": "knowledge",
        "source_agent": fragment.source_agent,
        "captured_at": fragment.captured_at,
        "provenance": dict(fragment.provenance),
        "supersedes": [],
        # derivation
        "distilled_from": session_ref,
        "fragment_ref": fragment_ref,
    }
    return Slice(slice_id=slice_id, frontmatter=frontmatter, body=body)


def validate(frontmatter: dict[str, object], body: str) -> list[str]:
    result = stage3.validate_frontmatter(frontmatter=frontmatter, body=body)
    errors = list(result.errors)
    for field in _T4_FIELDS:
        if field not in frontmatter:
            errors.append(f"missing T4 contract field: {field}")
    if frontmatter.get("memory_layer") != "knowledge":
        errors.append("memory_layer must be 'knowledge'")
    return errors


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def render(slice_: Slice) -> str:
    fm = slice_.frontmatter
    lines = ["---"]
    for key in _SCALAR_ORDER:
        if key not in fm:
            continue
        lines.append(f"{key}: {_scalar(fm[key])}")
    provenance = fm.get("provenance") or {}
    if isinstance(provenance, dict):
        lines.append("provenance:")
        for pkey in ("repo", "commit", "path"):
            lines.append(f"  {pkey}: {provenance.get(pkey, '')}")
    lines.append("---")
    return "\n".join(lines) + "\n" + slice_.body
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_slice_frontmatter -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/slice_frontmatter.py paulshaclaw/memory/tests/test_slice_frontmatter.py
git commit -m "feat(stage2): add T3 slice frontmatter builder"
```

---

## Task 6: `atomizer/promoter.py` — Promoter interface + IdentityPromoter (1:1)

**Files:**
- Create: `paulshaclaw/memory/atomizer/promoter.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_promoter.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_promoter.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import promoter
from paulshaclaw.memory.atomizer.config import AtomizerConfig
from paulshaclaw.memory.atomizer.splitter import Fragment

CFG = AtomizerConfig(schema_version="1", boundary_patterns=(r"^#{1,6}\s",), max_fragment_chars=8000,
                     artifact_kind_map={"research": "research"}, phase_map={"research": "research"},
                     default_artifact_kind="report", default_phase="review")


def _frag():
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact="research", captured_at="2026-05-31T00:00:00Z",
                    provenance={"repo": "r", "commit": "c", "path": "p"}, fragment_index=0, body="alpha")


class PromoterTests(unittest.TestCase):
    def test_identity_promoter_is_one_to_one(self):
        slices = promoter.IdentityPromoter().promote(_frag(), CFG)
        self.assertEqual(len(slices), 1)

    def test_slice_carries_derivation(self):
        s = promoter.IdentityPromoter().promote(_frag(), CFG)[0]
        self.assertEqual(s.frontmatter["distilled_from"], "claude:s1")
        self.assertEqual(s.frontmatter["fragment_ref"], "claude__s1__000")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_promoter -v`
Expected: FAIL with `ImportError: cannot import name 'promoter'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/promoter.py
from __future__ import annotations

from abc import ABC, abstractmethod

from . import slice_frontmatter
from .config import AtomizerConfig
from .slice_frontmatter import Slice
from .splitter import Fragment


class Promoter(ABC):
    """Maps one fragment to one or more knowledge slices.

    The MVP IdentityPromoter is 1:1. A future LLM promoter (T3.2) replaces only
    this seam to perform semantic split/merge, relation inference, and tagging.
    """

    @abstractmethod
    def promote(self, fragment: Fragment, config: AtomizerConfig) -> list[Slice]:
        ...


class IdentityPromoter(Promoter):
    def promote(self, fragment: Fragment, config: AtomizerConfig) -> list[Slice]:
        return [slice_frontmatter.build(fragment, config)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_promoter -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/promoter.py paulshaclaw/memory/tests/test_atomizer_promoter.py
git commit -m "feat(stage2): add T3 promoter interface and 1:1 MVP"
```

---

## Task 7: `atomizer/pipeline.py` — two re-entrant passes

**Files:**
- Create: `paulshaclaw/memory/atomizer/pipeline.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py`

**Frontmatter reader:** reuse the same robust YAML frontmatter parse used by `janitor/record_source.py` (extract block between first two `---`, `yaml.safe_load`). Reproduce a small local `_parse_frontmatter` to avoid cross-coupling.

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_pipeline.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer import pipeline
from paulshaclaw.memory.ledger import processing

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha body
# Topic B
beta body
"""


def _seed_raw(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(_RAW, encoding="utf-8")
    return raw


class PipelineTests(unittest.TestCase):
    def test_split_pass_creates_fragments_and_archives_raw(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertFalse(raw.exists())  # raw archived out of raw layer
            self.assertTrue(list((root / "archive" / "sessions").rglob("*.md")))
            self.assertTrue(list((root / "knowledge").rglob("*.md")))
            self.assertEqual(processing.state_of(root, "claude:s1"), "promoted")

    def test_one_to_one_slice_count_matches_fragments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(result["summary"]["slices"], 2)  # two headings -> two slices

    def test_idempotent_second_run(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            kwargs = dict(config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            pipeline.run(root, **kwargs)
            before = len(list((root / "knowledge").rglob("*.md")))
            result2 = pipeline.run(root, **kwargs)
            self.assertEqual(result2["summary"]["slices"], 0)
            self.assertEqual(len(list((root / "knowledge").rglob("*.md"))), before)

    def test_flow_through_empties_working_layers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])
            self.assertTrue(list((root / "archive" / "fragments").rglob("*.md")))

    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z", dry_run=True)
            self.assertTrue(raw.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
            self.assertGreater(result["summary"]["slices"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline -v`
Expected: FAIL with `ImportError: cannot import name 'pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/pipeline.py
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from ..ledger import processing, relations
from . import slice_frontmatter, splitter
from .config import AtomizerConfig
from .promoter import IdentityPromoter, Promoter
from .splitter import Fragment


def _parse_frontmatter(text: str) -> tuple[Mapping[str, Any] | None, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, text
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    try:
        import yaml  # type: ignore[import-not-found]
        data = yaml.safe_load(block)
    except ModuleNotFoundError:
        data = None
    if not isinstance(data, dict):
        return None, body
    return data, body


def _month(captured_at: str, now: str) -> str:
    base = captured_at if captured_at[:7].count("-") == 1 else now
    return base[:7] if len(base) >= 7 else now[:7]


def _raw_session_docs(memory_root: Path) -> list[Path]:
    inbox = memory_root / "inbox"
    slices_dir = inbox / "_slices"
    docs: list[Path] = []
    for path in sorted(inbox.rglob("*.md")):
        if slices_dir in path.parents:
            continue
        docs.append(path)
    return docs


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _split_pass(memory_root: Path, config: AtomizerConfig, config_hash: str, now: str,
                dry_run: bool, warnings: list[str]) -> int:
    count = 0
    for raw_path in _raw_session_docs(memory_root):
        data, body = _parse_frontmatter(raw_path.read_text(encoding="utf-8"))
        if data is None or not data.get("project") or not data.get("source_session"):
            warnings.append(f"{raw_path}: unparseable or missing project/source_session; skipped")
            continue
        agent = str(data.get("source_agent", "_unknown"))
        session = str(data["source_session"])
        session_key = f"{agent}:{session}"
        if processing.state_of(memory_root, session_key) in {"split", "promoted"}:
            continue  # already processed; raw is residual -> just archive below
        project = str(data["project"])
        captured_at = str(data.get("captured_at", now))
        provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
        provenance = {k: str(provenance.get(k, "")) for k in ("repo", "commit", "path")}
        source_artifact = str(data.get("source_artifact", "session"))

        bodies = splitter.split(body, config)
        if dry_run:
            count += 1
            continue
        for index, frag_body in enumerate(bodies):
            frag_path = (memory_root / "inbox" / "_slices" / project
                         / f"{agent}__{session}__{index:03d}.md")
            _atomic_write(frag_path, _render_fragment(
                project, agent, session, source_artifact, captured_at, provenance, index, frag_body))
            relations.append_edge(memory_root, type="fragment_of",
                                  frm=f"fragment:{agent}__{session}__{index:03d}",
                                  to=f"session:{session_key}", now=now, config_hash=config_hash)
        processing.append_state(memory_root, session_key=session_key, state="split",
                                now=now, config_hash=config_hash, fragments=len(bodies))
        archive = memory_root / "archive" / "sessions" / _month(captured_at, now) / f"{agent}__{session}.md"
        _move(raw_path, archive)
        count += 1
    return count


def _render_fragment(project, agent, session, source_artifact, captured_at, provenance, index, body) -> str:
    lines = ["---", "memory_layer: inbox", f"project: {project}",
             f"source_agent: {agent}", f"source_session: {session}",
             f"source_artifact: {source_artifact}", f"captured_at: {captured_at}",
             "provenance:", f"  repo: {provenance.get('repo', '')}",
             f"  commit: {provenance.get('commit', '')}", f"  path: {provenance.get('path', '')}",
             f"fragment_index: {index}", f"parent_session_ref: {agent}:{session}", "---"]
    return "\n".join(lines) + "\n" + body


def _read_fragment(path: Path) -> Fragment | None:
    data, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
    if data is None or not data.get("project") or not data.get("source_session"):
        return None
    provenance = data.get("provenance") if isinstance(data.get("provenance"), dict) else {}
    provenance = {k: str(provenance.get(k, "")) for k in ("repo", "commit", "path")}
    return Fragment(project=str(data["project"]), source_agent=str(data.get("source_agent", "_unknown")),
                    source_session=str(data["source_session"]),
                    source_artifact=str(data.get("source_artifact", "session")),
                    captured_at=str(data.get("captured_at", "")), provenance=provenance,
                    fragment_index=int(data.get("fragment_index", 0)), body=body)


def _promote_pass(memory_root: Path, config: AtomizerConfig, config_hash: str, now: str,
                  dry_run: bool, promoter: Promoter, warnings: list[str]) -> int:
    slices_written = 0
    states = processing.fold_states(memory_root)
    for session_key, state in states.items():
        if state != "split":
            continue
        agent, _, session = session_key.partition(":")
        frag_dir_glob = sorted((memory_root / "inbox" / "_slices").rglob(f"{agent}__{session}__*.md"))
        if not frag_dir_glob:
            continue
        archived: list[Path] = []
        for frag_path in frag_dir_glob:
            fragment = _read_fragment(frag_path)
            if fragment is None:
                warnings.append(f"{frag_path}: unreadable fragment; skipped")
                continue
            slice_ = promoter.promote(fragment, config)[0]
            errors = slice_frontmatter.validate(slice_.frontmatter, slice_.body)
            if errors:
                warnings.append(f"{frag_path}: slice validation failed: {errors}; left in split")
                return slices_written  # leave session in split for retry
            if dry_run:
                slices_written += 1
                continue
            knowledge_path = memory_root / "knowledge" / fragment.project / f"{slice_.slice_id}.md"
            _atomic_write(knowledge_path, slice_frontmatter.render(slice_))
            relations.append_edge(memory_root, type="promoted_to",
                                  frm=f"fragment:{frag_path.stem}", to=f"slice:{slice_.slice_id}",
                                  now=now, config_hash=config_hash)
            relations.append_edge(memory_root, type="distilled_from",
                                  frm=f"slice:{slice_.slice_id}", to=f"session:{session_key}",
                                  now=now, config_hash=config_hash)
            archived.append(frag_path)
            slices_written += 1
        if dry_run:
            continue
        for frag_path in archived:
            dst = memory_root / "archive" / "fragments" / _month("", now) / frag_path.name
            _move(frag_path, dst)
        processing.append_state(memory_root, session_key=session_key, state="promoted",
                                now=now, config_hash=config_hash, slices=len(archived))
    return slices_written


def run(memory_root: Path, *, config: AtomizerConfig, config_hash: str, now: str,
        dry_run: bool = False, promoter: Promoter | None = None) -> dict[str, Any]:
    promoter = promoter or IdentityPromoter()
    warnings: list[str] = []
    split = _split_pass(memory_root, config, config_hash, now, dry_run, warnings)
    slices = _promote_pass(memory_root, config, config_hash, now, dry_run, promoter, warnings)
    return {
        "summary": {"split_sessions": split, "slices": slices, "skipped": len(warnings),
                    "config_hash": config_hash, "dry_run": dry_run},
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py
git commit -m "feat(stage2): add T3 atomizer two-pass pipeline"
```

---

## Task 8: `atomizer/cli.py` + wire into `memory/cli.py`

**Files:**
- Create: `paulshaclaw/memory/atomizer/cli.py`
- Modify: `paulshaclaw/memory/cli.py` (add `atomize` group; add `_atomize` handler)
- Test: `paulshaclaw/memory/tests/test_atomizer_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_cli.py
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import cli

_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha
"""


class AtomizeCliTests(unittest.TestCase):
    def test_dry_run_prints_summary_and_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True)
            raw.write_text(_RAW, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "atomize", "--memory-root", str(root),
                               "--now", "2026-05-31T03:00:00Z", "--dry-run"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertGreaterEqual(payload["summary"]["slices"], 1)
            self.assertTrue(raw.exists())
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_cli -v`
Expected: FAIL with `SystemExit: 2` / `invalid choice: 'atomize'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config as atomizer_config
from . import pipeline


def run(args: argparse.Namespace) -> int:
    override = args.override if getattr(args, "override", None) else atomizer_config._DEFAULT_SENTINEL
    config, config_hash = atomizer_config.load_config(override_path=override)
    result = pipeline.run(
        Path(args.memory_root),
        config=config,
        config_hash=config_hash,
        now=args.now,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
```

Then wire into `paulshaclaw/memory/cli.py`. In `_build_parser`, after the existing `janitor` block, add:

```python
    atomize = memory_subparsers.add_parser("atomize")
    atomize.add_argument("--memory-root", required=True)
    atomize.add_argument("--now", default=None)
    atomize.add_argument("--override", default=None)
    atomize.add_argument("--dry-run", action="store_true")
    atomize.set_defaults(func=_atomize)
```

And add this handler near the other `_*` handlers in `paulshaclaw/memory/cli.py`:

```python
def _atomize(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    from .atomizer.cli import run as atomize_run

    if args.now is None:
        args.now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return atomize_run(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_cli -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/cli.py paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_atomizer_cli.py
git commit -m "feat(stage2): wire psc memory atomize CLI"
```

---

## Task 9: E2E (crash-resume / reimport / fail-closed / cross-stage) + integration + routing

**Files:**
- Create: `paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md`
- Test: `paulshaclaw/memory/tests/test_atomizer_e2e.py`
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`
- Modify: `paulshaclaw/memory/routing.md`

- [ ] **Step 1: Create the fixture**

```markdown
<!-- paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md (strip this comment line) -->
---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: sess-e2e
source_artifact: research
captured_at: "2026-05-31T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
# Topic A
alpha body
# Topic B
beta body
```

- [ ] **Step 2: Write the failing E2E test**

```python
# paulshaclaw/memory/tests/test_atomizer_e2e.py
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import config as atomizer_config
from paulshaclaw.memory.atomizer import pipeline
from paulshaclaw.memory.ledger import processing, relations
from paulshaclaw.lifecycle.schema import parse_artifact_text, validate_frontmatter

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "atomizer" / "raw" / "s1.md"
REPO_ROOT = Path(__file__).resolve().parents[3]


def _seed(root: Path) -> Path:
    raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURE, raw)
    return raw


def _cfg():
    return atomizer_config.load_config(override_path=None)


class AtomizerE2ETests(unittest.TestCase):
    def test_full_run_then_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "promoted")
            r2 = pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T04:00:00Z")
            self.assertEqual(r2["summary"]["slices"], 0)

    def test_crash_resume_promote_completes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            # Simulate split done but promote not: run split_pass only.
            warnings: list[str] = []
            pipeline._split_pass(root, cfg, h, "2026-05-31T03:00:00Z", False, warnings)
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "split")
            self.assertTrue(list((root / "inbox" / "_slices").rglob("*.md")))
            # Full run resumes and promotes.
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:30:00Z")
            self.assertEqual(processing.state_of(root, "claude:sess-e2e"), "promoted")
            self.assertEqual(list((root / "inbox" / "_slices").rglob("*.md")), [])

    def test_reimport_overwrites_same_slice_id(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            slice_files = list((root / "knowledge").rglob("*.md"))
            ids_before = sorted(p.name for p in slice_files)
            # Re-import same session with changed body.
            raw = root / "inbox" / "research" / "claude" / "2026-05-31" / "s1.md"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_text(FIXTURE.read_text(encoding="utf-8").replace("alpha body", "ALPHA v2"),
                           encoding="utf-8")
            # Clear processing so the re-imported raw is reprocessed (new evidence).
            # (In production a fresh import key/new run triggers reprocessing; here we
            #  reset state to exercise the overwrite path deterministically.)
            processing.processing_path(root).unlink()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T05:00:00Z")
            ids_after = sorted(p.name for p in (root / "knowledge").rglob("*.md"))
            self.assertEqual(ids_before, ids_after)  # same slice_id reused
            self.assertIn("ALPHA v2", (root / "knowledge" / "paulshaclaw" / ids_after[0]).read_text())

    def test_produced_slice_passes_stage3_gate(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            slice_path = next((root / "knowledge").rglob("*.md"))
            doc = parse_artifact_text(slice_path.read_text(encoding="utf-8"))
            result = validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body)
            self.assertTrue(result.ok, result.errors)

    def test_relations_have_distilled_from(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            edges = relations.neighbors(root, "session:claude:sess-e2e")
            self.assertTrue(any(e["type"] == "distilled_from" for e in edges))

    def test_ledgers_have_no_record_body(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root)
            cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-05-31T03:00:00Z")
            for name in ("processing.jsonl", "relations.jsonl"):
                raw = (root / "runtime" / "ledger" / name).read_text(encoding="utf-8")
                self.assertNotIn("alpha body", raw)
                self.assertNotIn("beta body", raw)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run E2E to verify, fixing implementation (not tests) on failure**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_e2e -v`
Expected: PASS (6 tests). If a scenario fails, fix `pipeline.py`/`splitter.py`, not the test.

- [ ] **Step 4: Wire the integration check + routing, run full regression**

Add to `paulshaclaw/memory/tests/stage2_integration_check.sh`, before `echo "[stage2] ok"`:

```bash
echo "[stage2] atomizer dry-run over fixtures"
ATOMIZE_ROOT="$(mktemp -d)"
mkdir -p "$ATOMIZE_ROOT/inbox/research/claude/2026-05-31"
cp "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md" \
   "$ATOMIZE_ROOT/inbox/research/claude/2026-05-31/s1.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory atomize \
  --memory-root "$ATOMIZE_ROOT" --now "2026-05-31T03:00:00Z" --dry-run | grep -Fq '"slices":'
```

Append to the `## 3. decayed/reactivation 事件流程` neighborhood of `paulshaclaw/memory/routing.md`:

```markdown

> **T3 已落地（2026-05）：** inbox raw session 由 `psc memory atomize` 經確定性結構拆分 → 1:1 升級為 `knowledge/<project>/<slice_id>.md`;處理狀態記於 `runtime/ledger/processing.jsonl`,派生關係記於 `runtime/ledger/relations.jsonl`。設計見 `docs/superpowers/specs/2026-05-31-stage2-t3-atomizer-linker-design.md`。
```

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`
Expected: PASS (all memory tests green)

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: ends with `[stage2] ok`

Run: `python3 -m unittest discover -s tests -v`
Expected: pre-existing unrelated failures only (flaky `tests/test_start_sh.py` timing, `tests/test_stage9_project_monitor.py` snapshot); no new T3 regressions.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/tests/fixtures/atomizer paulshaclaw/memory/tests/test_atomizer_e2e.py \
        paulshaclaw/memory/tests/stage2_integration_check.sh paulshaclaw/memory/routing.md
git commit -m "test(stage2): add T3 atomizer end-to-end and integration wiring"
```

---

## Verification Summary（實作完成後填）

（填入：`test_atomizer_*` / `test_ledger_processing` / `test_ledger_relations` / `test_slice_frontmatter` 聚焦結果、`unittest discover -s paulshaclaw/memory/tests` 全套結果、`stage2_integration_check.sh` 輸出、`lifecycle.gate` 跨 stage 驗證、`unittest discover -s tests` 回歸狀態。）
