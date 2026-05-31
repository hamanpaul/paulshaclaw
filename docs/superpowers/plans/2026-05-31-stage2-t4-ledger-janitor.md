# Stage 2 Topic 4 — Lifecycle Ledger + Minimal Janitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `lifecycle.jsonl` 治理 ledger 與一個確定性的最小 janitor，對 knowledge 層記錄做 decayed/reactivation 判斷，並提供高信任 active-set read API 供 Topic 7 消費。

**Architecture:** 純決策邏輯（`janitor/rules.py`）與 IO/orchestration（`janitor/scanner.py`、`ledger/*`）分離。ledger 為 append-only JSONL + flock。janitor 一次性掃描，從 `knowledge/` 記錄 + `import.jsonl` + `lifecycle.jsonl` 重算，冪等可重跑。

**Tech Stack:** Python 3.12、stdlib（`fcntl`/`json`/`hashlib`/`dataclasses`）、PyYAML（經既有 `_read_mapping` try/except 模式）、`unittest`。

**設計依據：** `docs/superpowers/specs/2026-05-31-stage2-t4-ledger-janitor-design.md`

**共用慣例（沿用既有 code）：**
- canonical json：`json.dumps(value, sort_keys=True, separators=(",", ":"))`
- flock：thread-lock + lock file（仿 `importer/pipeline.py::_locked_ledger`）
- yaml 載入：仿 `policy/loader.py::_read_mapping`
- hash：`hashlib.sha256(canonical_json(...).encode("utf-8")).hexdigest()`
- import.jsonl entry 既有欄位：`idempotency_key` / `status` / `recorded_at`(ISO) / `captured_at` / `content_hash`

---

## Task 1: `ledger/lifecycle.py` — 事件 IO + flock + 純 fold

**Files:**
- Create: `paulshaclaw/memory/ledger/__init__.py`
- Create: `paulshaclaw/memory/ledger/lifecycle.py`
- Test: `paulshaclaw/memory/tests/test_lifecycle_ledger.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_lifecycle_ledger.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle


def _decayed(rid: str, ts: str) -> dict:
    return {
        "schema_version": "1", "event_type": "decayed", "record_id": rid,
        "ts": ts, "reason": "ttl_expired", "detail": {"age_days": 100, "threshold_days": 90},
        "original_ref": {"slice_id": rid, "source_key": "claude:s1", "provenance": {}},
        "janitor_config_hash": "h1",
    }


def _reactivation(rid: str, ts: str) -> dict:
    return {
        "schema_version": "1", "event_type": "reactivation", "record_id": rid,
        "ts": ts, "reason": "reimport", "agent_ref": "claude:s1",
        "detail": {"import_status": "updated", "import_ts": ts}, "janitor_config_hash": "h1",
    }


class LifecycleLedgerTests(unittest.TestCase):
    def test_append_then_read_roundtrip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle.append_event(root, _decayed("sl-1", "2026-05-31T01:00:00Z"))
            events = lifecycle.read_events(root)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "decayed")
            self.assertEqual(events[0]["record_id"], "sl-1")

    def test_read_missing_ledger_returns_empty(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(lifecycle.read_events(Path(tmp)), [])

    def test_read_corrupt_line_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = lifecycle.lifecycle_path(root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"ok":1}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(lifecycle.LifecycleLedgerError):
                lifecycle.read_events(root)

    def test_fold_latest_event_wins(self):
        events = [_decayed("sl-1", "2026-05-31T01:00:00Z"),
                  _reactivation("sl-1", "2026-05-31T03:00:00Z")]
        state = lifecycle.fold(events)
        self.assertEqual(state["sl-1"]["state"], "active")
        self.assertEqual(state["sl-1"]["since_ts"], "2026-05-31T03:00:00Z")

    def test_fold_decayed_excludes(self):
        events = [_reactivation("sl-1", "2026-05-31T01:00:00Z"),
                  _decayed("sl-1", "2026-05-31T03:00:00Z")]
        state = lifecycle.fold(events)
        self.assertEqual(state["sl-1"]["state"], "decayed")

    def test_fold_out_of_order_uses_ts_not_append_order(self):
        # appended reactivation-then-decayed but ts says decayed is older
        events = [_decayed("sl-1", "2026-05-31T01:00:00Z"),
                  _reactivation("sl-1", "2026-05-31T05:00:00Z"),
                  _decayed("sl-1", "2026-05-31T03:00:00Z")]
        state = lifecycle.fold(events)
        self.assertEqual(state["sl-1"]["state"], "active")  # 05:00 reactivation is latest
        self.assertEqual(state["sl-1"]["since_ts"], "2026-05-31T05:00:00Z")

    def test_lines_are_canonical_json(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle.append_event(root, _decayed("sl-1", "2026-05-31T01:00:00Z"))
            raw = lifecycle.lifecycle_path(root).read_text(encoding="utf-8").strip()
            self.assertEqual(raw, json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_lifecycle_ledger -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.ledger'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/__init__.py
```

```python
# paulshaclaw/memory/ledger/lifecycle.py
from __future__ import annotations

import fcntl
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class LifecycleLedgerError(Exception):
    """Raised when the lifecycle ledger cannot be safely read or written."""


def lifecycle_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "lifecycle.jsonl"


def _lock_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "locks" / "lifecycle-ledger.lock"


def _thread_lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve(strict=False))
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


@contextmanager
def locked(memory_root: Path):
    lock_path = _lock_path(memory_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    thread_lock = _thread_lock_for(lock_path)
    with thread_lock:
        with lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)


def append_event(memory_root: Path, event: dict[str, Any]) -> None:
    path = lifecycle_path(memory_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def read_events(memory_root: Path) -> list[dict[str, Any]]:
    path = lifecycle_path(memory_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise LifecycleLedgerError(
                    f"corrupt lifecycle ledger at line {lineno}: {exc}"
                ) from exc
    return events


def fold(events: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """record_id -> {state, since_ts} using latest event by (ts, append index)."""
    indexed = sorted(enumerate(events), key=lambda pair: (pair[1].get("ts", ""), pair[0]))
    state: dict[str, dict[str, str]] = {}
    for _, event in indexed:
        rid = event.get("record_id")
        if rid is None:
            continue
        etype = event.get("event_type")
        if etype == "decayed":
            state[rid] = {"state": "decayed", "since_ts": event.get("ts", "")}
        elif etype == "reactivation":
            state[rid] = {"state": "active", "since_ts": event.get("ts", "")}
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_lifecycle_ledger -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/__init__.py paulshaclaw/memory/ledger/lifecycle.py paulshaclaw/memory/tests/test_lifecycle_ledger.py
git commit -m "feat(stage2): add T4 lifecycle ledger IO and fold"
```

---

## Task 2: `ledger/retrieval_set.py` — active-set read API（Topic 7 介面）

**Files:**
- Create: `paulshaclaw/memory/ledger/retrieval_set.py`
- Test: `paulshaclaw/memory/tests/test_retrieval_set.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_retrieval_set.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import lifecycle, retrieval_set


def _decayed(rid: str, ts: str) -> dict:
    return {"schema_version": "1", "event_type": "decayed", "record_id": rid, "ts": ts,
            "reason": "ttl_expired", "detail": {}, "original_ref": {}, "janitor_config_hash": "h"}


def _reactivation(rid: str, ts: str) -> dict:
    return {"schema_version": "1", "event_type": "reactivation", "record_id": rid, "ts": ts,
            "reason": "reimport", "agent_ref": "claude:s1", "detail": {}, "janitor_config_hash": "h"}


class RetrievalSetTests(unittest.TestCase):
    def test_no_events_means_active_by_default(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(retrieval_set.active_records(root, ["a", "b"]), ["a", "b"])
            self.assertEqual(retrieval_set.record_state(root, "a"), "active")

    def test_decayed_excluded_reactivation_included(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            lifecycle.append_event(root, _decayed("a", "2026-05-31T01:00:00Z"))
            lifecycle.append_event(root, _decayed("b", "2026-05-31T01:00:00Z"))
            lifecycle.append_event(root, _reactivation("b", "2026-05-31T02:00:00Z"))
            self.assertEqual(retrieval_set.active_records(root, ["a", "b", "c"]), ["b", "c"])
            self.assertEqual(retrieval_set.record_state(root, "a"), "decayed")
            self.assertEqual(retrieval_set.record_state(root, "b"), "active")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_retrieval_set -v`
Expected: FAIL with `ImportError: cannot import name 'retrieval_set'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/retrieval_set.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import lifecycle


def fold_states(memory_root: Path) -> dict[str, str]:
    detail = lifecycle.fold(lifecycle.read_events(memory_root))
    return {rid: info["state"] for rid, info in detail.items()}


def record_state(memory_root: Path, record_id: str) -> str:
    return fold_states(memory_root).get(record_id, "active")


def active_records(memory_root: Path, candidate_ids: Iterable[str]) -> list[str]:
    states = fold_states(memory_root)
    return [rid for rid in candidate_ids if states.get(rid, "active") == "active"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_retrieval_set -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/retrieval_set.py paulshaclaw/memory/tests/test_retrieval_set.py
git commit -m "feat(stage2): add T4 active-set retrieval API"
```

---

## Task 3: `ledger/import_log.py` — 讀 import.jsonl（reactivation 訊號）

**Files:**
- Create: `paulshaclaw/memory/ledger/import_log.py`
- Test: `paulshaclaw/memory/tests/test_import_log.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_import_log.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.ledger import import_log


def _seed(root: Path, entries: list[dict]) -> None:
    path = root / "runtime" / "ledger" / "import.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


class ImportLogTests(unittest.TestCase):
    def test_missing_file_returns_empty(self):
        with TemporaryDirectory() as tmp:
            self.assertEqual(import_log.events_for_session(Path(tmp), "claude:s1"), [])

    def test_returns_only_written_or_updated_for_key(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed(root, [
                {"idempotency_key": "claude:s1", "status": "written", "recorded_at": "2026-05-31T01:00:00Z"},
                {"idempotency_key": "claude:s1", "status": "hash-duplicate", "recorded_at": "2026-05-31T02:00:00Z"},
                {"idempotency_key": "claude:s2", "status": "written", "recorded_at": "2026-05-31T03:00:00Z"},
                {"idempotency_key": "claude:s1", "status": "updated", "recorded_at": "2026-05-31T04:00:00Z"},
            ])
            got = import_log.events_for_session(root, "claude:s1")
            self.assertEqual([e["status"] for e in got], ["written", "updated"])

    def test_corrupt_line_is_skipped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "runtime" / "ledger" / "import.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '{"idempotency_key":"claude:s1","status":"written","recorded_at":"t1"}\n'
                'broken\n',
                encoding="utf-8",
            )
            got = import_log.events_for_session(root, "claude:s1")
            self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_import_log -v`
Expected: FAIL with `ImportError: cannot import name 'import_log'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/ledger/import_log.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_RELEVANT = {"written", "updated"}


def import_log_path(memory_root: Path) -> Path:
    return memory_root / "runtime" / "ledger" / "import.jsonl"


def iter_import_events(memory_root: Path) -> list[dict[str, Any]]:
    path = import_log_path(memory_root)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue  # auxiliary signal: skip corrupt line, never fail-closed
    return events


def events_for_session(memory_root: Path, source_key: str) -> list[dict[str, Any]]:
    return [
        event
        for event in iter_import_events(memory_root)
        if event.get("idempotency_key") == source_key and event.get("status") in _RELEVANT
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_import_log -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/import_log.py paulshaclaw/memory/tests/test_import_log.py
git commit -m "feat(stage2): add T4 import-log read API"
```

---

## Task 4: `janitor/config.py` + `lifecycle.yaml` — 設定 loader + hash

**Files:**
- Create: `paulshaclaw/memory/janitor/__init__.py`
- Create: `paulshaclaw/memory/janitor/lifecycle.yaml`
- Create: `paulshaclaw/memory/janitor/config.py`
- Test: `paulshaclaw/memory/tests/test_janitor_config.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_janitor_config.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.janitor import config as janitor_config


class JanitorConfigTests(unittest.TestCase):
    def test_load_defaults(self):
        cfg, cfg_hash = janitor_config.load_config(override_path=None)
        self.assertEqual(cfg.default_decay_age_days, 90)
        self.assertTrue(cfg.check_provenance_path)
        self.assertTrue(cfg.decay_superseded)
        self.assertEqual(len(cfg_hash), 64)

    def test_override_merges_and_changes_hash(self):
        _, base_hash = janitor_config.load_config(override_path=None)
        with TemporaryDirectory() as tmp:
            override = Path(tmp) / "janitor.override.yaml"
            override.write_text("ttl:\n  default_decay_age_days: 7\n", encoding="utf-8")
            cfg, cfg_hash = janitor_config.load_config(override_path=override)
            self.assertEqual(cfg.default_decay_age_days, 7)
            self.assertTrue(cfg.check_provenance_path)  # untouched default preserved
            self.assertNotEqual(cfg_hash, base_hash)

    def test_unsupported_schema_version_fails_closed(self):
        with TemporaryDirectory() as tmp:
            bad_dir = Path(tmp)
            (bad_dir / "lifecycle.yaml").write_text("schema_version: 999\n", encoding="utf-8")
            with self.assertRaises(janitor_config.JanitorConfigError):
                janitor_config.load_config(default_dir=bad_dir, override_path=None)

    def test_hash_is_deterministic(self):
        _, h1 = janitor_config.load_config(override_path=None)
        _, h2 = janitor_config.load_config(override_path=None)
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_config -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.janitor'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/janitor/__init__.py
```

```yaml
# paulshaclaw/memory/janitor/lifecycle.yaml
schema_version: 1
ttl:
  default_decay_age_days: 90
  by_artifact_kind: {}
source_checks:
  check_provenance_path: true
  check_provenance_commit: false
supersede:
  decay_superseded: true
```

```python
# paulshaclaw/memory/janitor/config.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent
SUPPORTED_SCHEMA = "1"
_USE_DEFAULT_OVERRIDE = object()


class JanitorConfigError(Exception):
    """Raised when janitor config is invalid or unsupported (fail-closed)."""


@dataclass(frozen=True)
class JanitorConfig:
    schema_version: str
    default_decay_age_days: int
    by_artifact_kind: dict[str, int] = field(default_factory=dict)
    check_provenance_path: bool = True
    check_provenance_commit: bool = False
    decay_superseded: bool = True


def _read_mapping(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, Mapping):
        raise JanitorConfigError(f"janitor config must be a mapping: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_override(override_path: str | Path | None | object) -> Path | None:
    if override_path is _USE_DEFAULT_OVERRIDE:
        return Path.home() / ".config" / "paulshaclaw" / "janitor.override.yaml"
    if override_path is None:
        return None
    return Path(override_path)


def load_config(
    default_dir: str | Path | None = None,
    override_path: str | Path | None | object = _USE_DEFAULT_OVERRIDE,
) -> tuple[JanitorConfig, str]:
    config_dir = Path(default_dir) if default_dir is not None else DEFAULT_CONFIG_DIR
    effective = dict(_read_mapping(config_dir / "lifecycle.yaml"))

    override_file = _resolve_override(override_path)
    if override_file is not None and override_file.exists():
        effective = _deep_merge(effective, _read_mapping(override_file))

    if str(effective.get("schema_version", "")) != SUPPORTED_SCHEMA:
        raise JanitorConfigError(
            f"unsupported janitor schema_version: {effective.get('schema_version')}"
        )

    ttl = effective.get("ttl", {})
    source_checks = effective.get("source_checks", {})
    supersede = effective.get("supersede", {})
    config = JanitorConfig(
        schema_version=SUPPORTED_SCHEMA,
        default_decay_age_days=int(ttl.get("default_decay_age_days", 90)),
        by_artifact_kind={str(k): int(v) for k, v in (ttl.get("by_artifact_kind") or {}).items()},
        check_provenance_path=bool(source_checks.get("check_provenance_path", True)),
        check_provenance_commit=bool(source_checks.get("check_provenance_commit", False)),
        decay_superseded=bool(supersede.get("decay_superseded", True)),
    )
    config_hash = hashlib.sha256(
        json.dumps(effective, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return config, config_hash
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_config -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/janitor/__init__.py paulshaclaw/memory/janitor/lifecycle.yaml paulshaclaw/memory/janitor/config.py paulshaclaw/memory/tests/test_janitor_config.py
git commit -m "feat(stage2): add T4 janitor config loader"
```

---

## Task 5: `janitor/record_source.py` — knowledge 記錄讀取契約

**Files:**
- Create: `paulshaclaw/memory/janitor/record_source.py`
- Test: `paulshaclaw/memory/tests/test_janitor_record_source.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_janitor_record_source.py
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.janitor import record_source


_KNOWLEDGE = """---
memory_layer: knowledge
slice_id: sl-1
supersedes:
  - sl-0
project: paulshaclaw
source_agent: claude
source_session: sess-abc
source_artifact: a.md
captured_at: "2026-01-01T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: deadbeef
  path: docs/x.md
---
body
"""

_INBOX = """---
memory_layer: inbox
slice_id: sl-9
source_agent: claude
source_session: sess-z
captured_at: "2026-01-01T00:00:00Z"
---
body
"""

_NO_SLICE = """---
memory_layer: knowledge
source_agent: claude
source_session: sess-q
captured_at: "2026-01-01T00:00:00Z"
---
body
"""


def _write(root: Path, name: str, text: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")


class RecordSourceTests(unittest.TestCase):
    def test_reads_knowledge_record_fields(self):
        with TemporaryDirectory() as tmp:
            kroot = Path(tmp) / "knowledge"
            _write(kroot, "a.md", _KNOWLEDGE)
            records, warnings = record_source.iter_records(kroot)
            self.assertEqual(warnings, [])
            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertEqual(rec.record_id, "sl-1")
            self.assertEqual(rec.supersedes, ("sl-0",))
            self.assertEqual(rec.source_key, "claude:sess-abc")
            self.assertEqual(rec.captured_at, "2026-01-01T00:00:00Z")
            self.assertEqual(rec.provenance["path"], "docs/x.md")

    def test_skips_non_knowledge_layer(self):
        with TemporaryDirectory() as tmp:
            kroot = Path(tmp) / "knowledge"
            _write(kroot, "b.md", _INBOX)
            records, warnings = record_source.iter_records(kroot)
            self.assertEqual(records, [])
            self.assertEqual(warnings, [])

    def test_missing_slice_id_warns_and_skips(self):
        with TemporaryDirectory() as tmp:
            kroot = Path(tmp) / "knowledge"
            _write(kroot, "c.md", _NO_SLICE)
            records, warnings = record_source.iter_records(kroot)
            self.assertEqual(records, [])
            self.assertEqual(len(warnings), 1)
            self.assertIn("slice_id", warnings[0])

    def test_missing_root_returns_empty(self):
        with TemporaryDirectory() as tmp:
            records, warnings = record_source.iter_records(Path(tmp) / "nope")
            self.assertEqual(records, [])
            self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_record_source -v`
Expected: FAIL with `ImportError: cannot import name 'record_source'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/janitor/record_source.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    supersedes: tuple[str, ...]
    source_key: str
    captured_at: str
    provenance: dict[str, str]
    path: Path


def _parse_frontmatter(text: str) -> Mapping[str, Any] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            block = "\n".join(lines[1:index])
            break
    else:
        return None
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return json.loads(block) if block.strip().startswith("{") else None
    data = yaml.safe_load(block)
    return data if isinstance(data, Mapping) else None


def _build_record(path: Path, data: Mapping[str, Any]) -> tuple[KnowledgeRecord | None, str | None]:
    if str(data.get("memory_layer", "")) != "knowledge":
        return None, None
    slice_id = data.get("slice_id")
    if not slice_id:
        return None, f"{path}: missing slice_id; skipped"
    supersedes_raw = data.get("supersedes") or []
    if isinstance(supersedes_raw, str):
        supersedes_raw = [supersedes_raw]
    provenance_raw = data.get("provenance") or {}
    provenance = {
        "repo": str(provenance_raw.get("repo", "")),
        "commit": str(provenance_raw.get("commit", "")),
        "path": str(provenance_raw.get("path", "")),
    }
    source_key = f"{data.get('source_agent', '_unknown')}:{data.get('source_session', '_unknown')}"
    record = KnowledgeRecord(
        record_id=str(slice_id),
        supersedes=tuple(str(item) for item in supersedes_raw),
        source_key=source_key,
        captured_at=str(data.get("captured_at", "")),
        provenance=provenance,
        path=path,
    )
    return record, None


def iter_records(knowledge_root: Path) -> tuple[list[KnowledgeRecord], list[str]]:
    records: list[KnowledgeRecord] = []
    warnings: list[str] = []
    if not knowledge_root.exists():
        return records, warnings
    for path in sorted(knowledge_root.rglob("*.md")):
        data = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if data is None:
            warnings.append(f"{path}: unparseable frontmatter; skipped")
            continue
        record, warning = _build_record(path, data)
        if warning is not None:
            warnings.append(warning)
        if record is not None:
            records.append(record)
    return records, warnings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_record_source -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/janitor/record_source.py paulshaclaw/memory/tests/test_janitor_record_source.py
git commit -m "feat(stage2): add T4 knowledge record source"
```

---

## Task 6: `janitor/rules.py` — 純決策邏輯（decay + reactivation）

**Files:**
- Create: `paulshaclaw/memory/janitor/rules.py`
- Test: `paulshaclaw/memory/tests/test_janitor_rules.py`

**注意：** `plan_scan` 為純函式。`source_path_exists` 是注入的可呼叫（預設檢查實檔），測試以 lambda 覆寫以保持確定性；回傳 `None` 表「無法判定」→ fail-safe 不 decay。

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_janitor_rules.py
from __future__ import annotations

import unittest
from pathlib import Path

from paulshaclaw.memory.janitor import rules
from paulshaclaw.memory.janitor.config import JanitorConfig
from paulshaclaw.memory.janitor.record_source import KnowledgeRecord

CFG = JanitorConfig(schema_version="1", default_decay_age_days=90, by_artifact_kind={},
                    check_provenance_path=True, check_provenance_commit=False, decay_superseded=True)
HASH = "cfg-hash"
NOW = "2026-05-31T00:00:00Z"


def _rec(rid="sl-1", supersedes=(), source="claude:s1", captured="2026-01-01T00:00:00Z", path="docs/x.md"):
    return KnowledgeRecord(record_id=rid, supersedes=tuple(supersedes), source_key=source,
                           captured_at=captured, provenance={"repo": "r", "commit": "c", "path": path}, path=Path("/tmp/x.md"))


# default: path exists, so source_invalid never fires unless overridden
_PATH_OK = lambda rec: True


class DecayRuleTests(unittest.TestCase):
    def test_ttl_expired_decays(self):
        events = rules.plan_scan([_rec(captured="2020-01-01T00:00:00Z")], {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "decayed")
        self.assertEqual(events[0]["reason"], "ttl_expired")
        self.assertEqual(events[0]["ts"], NOW)

    def test_fresh_record_stays_active(self):
        events = rules.plan_scan([_rec(captured="2026-05-30T00:00:00Z")], {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])

    def test_superseded_beats_ttl(self):
        # sl-1 is old (would TTL) AND superseded by sl-7 -> reason must be superseded
        recs = [_rec(rid="sl-1", captured="2020-01-01T00:00:00Z"),
                _rec(rid="sl-7", supersedes=("sl-1",), captured="2026-05-30T00:00:00Z")]
        events = rules.plan_scan(recs, {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        decayed = [e for e in events if e["record_id"] == "sl-1"]
        self.assertEqual(decayed[0]["reason"], "superseded")
        self.assertEqual(decayed[0]["detail"]["superseded_by"], "sl-7")

    def test_source_invalid_when_path_missing(self):
        events = rules.plan_scan([_rec(captured="2026-05-30T00:00:00Z")], {}, {}, CFG, NOW, HASH,
                                 source_path_exists=lambda rec: False)
        self.assertEqual(events[0]["reason"], "source_invalid")

    def test_source_unknown_does_not_decay_source(self):
        # path unknown (None) -> fail-safe, no source_invalid; record is fresh -> stays active
        events = rules.plan_scan([_rec(captured="2026-05-30T00:00:00Z")], {}, {}, CFG, NOW, HASH,
                                 source_path_exists=lambda rec: None)
        self.assertEqual(events, [])

    def test_already_decayed_record_not_redecayed(self):
        lc_state = {"sl-1": {"state": "decayed", "since_ts": "2026-04-01T00:00:00Z"}}
        events = rules.plan_scan([_rec(captured="2020-01-01T00:00:00Z")], {}, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])  # decayed records only evaluate reactivation

    def test_decayed_event_carries_original_ref(self):
        events = rules.plan_scan([_rec(captured="2020-01-01T00:00:00Z")], {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events[0]["original_ref"]["slice_id"], "sl-1")
        self.assertEqual(events[0]["original_ref"]["source_key"], "claude:s1")


class ReactivationRuleTests(unittest.TestCase):
    def test_reimport_after_decay_reactivates(self):
        lc_state = {"sl-1": {"state": "decayed", "since_ts": "2026-03-01T00:00:00Z"}}
        import_index = {"claude:s1": [{"status": "updated", "recorded_at": "2026-04-01T00:00:00Z"}]}
        events = rules.plan_scan([_rec()], import_index, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events[0]["event_type"], "reactivation")
        self.assertEqual(events[0]["agent_ref"], "claude:s1")
        self.assertEqual(events[0]["detail"]["import_ts"], "2026-04-01T00:00:00Z")

    def test_reimport_before_decay_does_not_reactivate(self):
        lc_state = {"sl-1": {"state": "decayed", "since_ts": "2026-05-01T00:00:00Z"}}
        import_index = {"claude:s1": [{"status": "written", "recorded_at": "2026-01-01T00:00:00Z"}]}
        events = rules.plan_scan([_rec()], import_index, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])

    def test_no_import_does_not_reactivate(self):
        lc_state = {"sl-1": {"state": "decayed", "since_ts": "2026-03-01T00:00:00Z"}}
        events = rules.plan_scan([_rec()], {}, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])

    def test_unknown_source_key_does_not_reactivate(self):
        lc_state = {"sl-1": {"state": "decayed", "since_ts": "2026-03-01T00:00:00Z"}}
        import_index = {"claude:_unknown": [{"status": "updated", "recorded_at": "2026-04-01T00:00:00Z"}]}
        events = rules.plan_scan([_rec(source="claude:_unknown")], import_index, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])

    def test_anti_flap_reactivated_record_not_immediately_redecayed(self):
        # old captured_at, but reactivated yesterday -> TTL base = reactivation ts -> stays active
        lc_state = {"sl-1": {"state": "active", "since_ts": "2026-05-30T00:00:00Z"}}
        events = rules.plan_scan([_rec(captured="2020-01-01T00:00:00Z")], {}, lc_state, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(events, [])


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_same_plan(self):
        recs = [_rec(captured="2020-01-01T00:00:00Z")]
        a = rules.plan_scan(recs, {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        b = rules.plan_scan(recs, {}, {}, CFG, NOW, HASH, source_path_exists=_PATH_OK)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_rules -v`
Expected: FAIL with `ImportError: cannot import name 'rules'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/janitor/rules.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .config import JanitorConfig
from .record_source import KnowledgeRecord

SCHEMA_VERSION = "1"

# Returns True (exists), False (definitely gone), or None (cannot determine -> fail-safe)
SourcePathCheck = Callable[[KnowledgeRecord], bool | None]


def _default_source_path_exists(record: KnowledgeRecord) -> bool | None:
    from pathlib import Path

    path_value = record.provenance.get("path", "")
    if not path_value:
        return None
    repo = record.provenance.get("repo", "")
    if not repo:
        return None  # cannot resolve a relative path without a known repo root
    candidate = Path(repo) / path_value
    return candidate.exists()


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_days(base: datetime, now: datetime) -> float:
    return (now - base).total_seconds() / 86400.0


def _ttl_base(record: KnowledgeRecord, lc_info: Mapping[str, str] | None) -> datetime | None:
    captured = _parse_ts(record.captured_at)
    if lc_info and lc_info.get("state") == "active":
        reactivated = _parse_ts(lc_info.get("since_ts", ""))
        if reactivated is not None and (captured is None or reactivated > captured):
            return reactivated
    return captured


def _decide_decay(
    record: KnowledgeRecord,
    superseded_by: Mapping[str, str],
    lc_info: Mapping[str, str] | None,
    config: JanitorConfig,
    now: datetime,
    source_path_exists: SourcePathCheck,
) -> tuple[str, dict[str, Any]] | None:
    if config.decay_superseded and record.record_id in superseded_by:
        return "superseded", {"superseded_by": superseded_by[record.record_id]}
    if config.check_provenance_path:
        exists = source_path_exists(record)
        if exists is False:  # only decay on a definite negative (fail-safe)
            return "source_invalid", {"source_check": "path", "ref": record.provenance.get("path", "")}
    base = _ttl_base(record, lc_info)
    if base is not None:
        threshold = config.default_decay_age_days
        age = _age_days(base, now)
        if age > threshold:
            return "ttl_expired", {"age_days": round(age, 3), "threshold_days": threshold}
    return None


def _decide_reactivation(
    record: KnowledgeRecord,
    import_index: Mapping[str, Sequence[Mapping[str, Any]]],
    decay_since_ts: str,
) -> dict[str, Any] | None:
    if record.source_key.endswith(":_unknown") or record.source_key.startswith("_unknown"):
        return None
    candidates = [
        event
        for event in import_index.get(record.source_key, [])
        if str(event.get("recorded_at", "")) > decay_since_ts
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda event: str(event.get("recorded_at", "")))
    return {"import_status": latest.get("status", ""), "import_ts": latest.get("recorded_at", "")}


def _decayed_event(record, reason, detail, now_str, config_hash):
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": "decayed",
        "record_id": record.record_id,
        "ts": now_str,
        "reason": reason,
        "detail": detail,
        "original_ref": {
            "slice_id": record.record_id,
            "source_key": record.source_key,
            "provenance": dict(record.provenance),
        },
        "janitor_config_hash": config_hash,
    }


def _reactivation_event(record, detail, now_str, config_hash):
    return {
        "schema_version": SCHEMA_VERSION,
        "event_type": "reactivation",
        "record_id": record.record_id,
        "ts": now_str,
        "reason": "reimport",
        "agent_ref": record.source_key,
        "detail": detail,
        "janitor_config_hash": config_hash,
    }


def plan_scan(
    records: Sequence[KnowledgeRecord],
    import_index: Mapping[str, Sequence[Mapping[str, Any]]],
    lc_state: Mapping[str, Mapping[str, str]],
    config: JanitorConfig,
    now: str,
    config_hash: str,
    source_path_exists: SourcePathCheck = _default_source_path_exists,
) -> list[dict[str, Any]]:
    now_dt = _parse_ts(now) or datetime.now(timezone.utc)
    superseded_by: dict[str, str] = {}
    for record in records:
        for sid in record.supersedes:
            superseded_by.setdefault(sid, record.record_id)

    events: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda r: r.record_id):
        info = lc_state.get(record.record_id)
        state = info["state"] if info else "active"
        if state == "active":
            decay = _decide_decay(record, superseded_by, info, config, now_dt, source_path_exists)
            if decay is not None:
                reason, detail = decay
                events.append(_decayed_event(record, reason, detail, now, config_hash))
        else:  # decayed -> only reactivation
            detail = _decide_reactivation(record, import_index, info.get("since_ts", ""))
            if detail is not None:
                events.append(_reactivation_event(record, detail, now, config_hash))
    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_rules -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/janitor/rules.py paulshaclaw/memory/tests/test_janitor_rules.py
git commit -m "feat(stage2): add T4 janitor decay/reactivation rules"
```

---

## Task 7: `janitor/scanner.py` — orchestrator `run_scan`

**Files:**
- Create: `paulshaclaw/memory/janitor/scanner.py`
- Test: `paulshaclaw/memory/tests/test_janitor_scanner.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_janitor_scanner.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.janitor import config as janitor_config
from paulshaclaw.memory.janitor import scanner
from paulshaclaw.memory.ledger import lifecycle


_OLD_RECORD = """---
memory_layer: knowledge
slice_id: sl-1
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: a.md
captured_at: "2020-01-01T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
body
"""


def _setup(tmp: str) -> tuple[Path, Path]:
    root = Path(tmp)
    kroot = root / "knowledge"
    kroot.mkdir(parents=True, exist_ok=True)
    (kroot / "sl-1.md").write_text(_OLD_RECORD, encoding="utf-8")
    return root, kroot


class ScannerTests(unittest.TestCase):
    def test_scan_writes_decayed_event(self):
        with TemporaryDirectory() as tmp:
            root, kroot = _setup(tmp)
            cfg, cfg_hash = janitor_config.load_config(override_path=None)
            result = scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=cfg_hash,
                                      now="2026-05-31T00:00:00Z", source_path_exists=lambda r: True)
            self.assertEqual(result["summary"]["decayed"], 1)
            events = lifecycle.read_events(root)
            self.assertEqual(events[0]["reason"], "ttl_expired")

    def test_idempotent_second_run_emits_nothing(self):
        with TemporaryDirectory() as tmp:
            root, kroot = _setup(tmp)
            cfg, cfg_hash = janitor_config.load_config(override_path=None)
            kwargs = dict(knowledge_root=kroot, config=cfg, config_hash=cfg_hash,
                          now="2026-05-31T00:00:00Z", source_path_exists=lambda r: True)
            scanner.run_scan(root, **kwargs)
            result2 = scanner.run_scan(root, **kwargs)
            self.assertEqual(result2["summary"]["decayed"], 0)
            self.assertEqual(len(lifecycle.read_events(root)), 1)

    def test_dry_run_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root, kroot = _setup(tmp)
            cfg, cfg_hash = janitor_config.load_config(override_path=None)
            result = scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=cfg_hash,
                                      now="2026-05-31T00:00:00Z", dry_run=True, source_path_exists=lambda r: True)
            self.assertEqual(len(result["plan"]), 1)
            self.assertEqual(lifecycle.read_events(root), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_scanner -v`
Expected: FAIL with `ImportError: cannot import name 'scanner'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/janitor/scanner.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ledger import import_log, lifecycle
from . import config as janitor_config
from . import record_source, rules


def run_scan(
    memory_root: Path,
    knowledge_root: Path | None = None,
    config: janitor_config.JanitorConfig | None = None,
    config_hash: str | None = None,
    now: str | None = None,
    dry_run: bool = False,
    source_path_exists: rules.SourcePathCheck = rules._default_source_path_exists,
) -> dict[str, Any]:
    if now is None:
        now = datetime.now(timezone.utc).isoformat()
    if config is None or config_hash is None:
        config, config_hash = janitor_config.load_config()
    if knowledge_root is None:
        knowledge_root = memory_root / "knowledge"

    records, warnings = record_source.iter_records(knowledge_root)
    lc_state = lifecycle.fold(lifecycle.read_events(memory_root))  # raises on corrupt -> fail-closed
    import_index = {
        record.source_key: import_log.events_for_session(memory_root, record.source_key)
        for record in records
    }

    plan = rules.plan_scan(
        records, import_index, lc_state, config, now, config_hash,
        source_path_exists=source_path_exists,
    )

    if not dry_run and plan:
        with lifecycle.locked(memory_root):
            for event in plan:
                lifecycle.append_event(memory_root, event)

    decayed = sum(1 for event in plan if event["event_type"] == "decayed")
    reactivated = sum(1 for event in plan if event["event_type"] == "reactivation")
    summary = {
        "scanned": len(records),
        "decayed": decayed,
        "reactivated": reactivated,
        "unchanged": len(records) - decayed - reactivated,
        "skipped": len(warnings),
        "config_hash": config_hash,
        "dry_run": dry_run,
    }
    return {"summary": summary, "plan": plan, "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_scanner -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/janitor/scanner.py paulshaclaw/memory/tests/test_janitor_scanner.py
git commit -m "feat(stage2): add T4 janitor scan orchestrator"
```

---

## Task 8: `janitor/cli.py` + wire into `memory/cli.py` — `psc memory janitor scan`

**Files:**
- Create: `paulshaclaw/memory/janitor/cli.py`
- Modify: `paulshaclaw/memory/cli.py`（在 `_build_parser` 增 `janitor` 群組；新增 `_janitor_scan`）
- Test: `paulshaclaw/memory/tests/test_janitor_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_janitor_cli.py
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import cli


_OLD_RECORD = """---
memory_layer: knowledge
slice_id: sl-1
project: paulshaclaw
source_agent: claude
source_session: s1
source_artifact: a.md
captured_at: "2020-01-01T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
body
"""


class JanitorCliTests(unittest.TestCase):
    def test_scan_dry_run_prints_summary_and_writes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            kroot.mkdir(parents=True)
            (kroot / "sl-1.md").write_text(_OLD_RECORD, encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main([
                    "memory", "janitor", "scan",
                    "--memory-root", str(root),
                    "--knowledge-root", str(kroot),
                    "--now", "2026-05-31T00:00:00Z",
                    "--dry-run",
                ])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["summary"]["decayed"], 1)
            self.assertFalse((root / "runtime" / "ledger" / "lifecycle.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_cli -v`
Expected: FAIL with `SystemExit: 2` / `invalid choice: 'janitor'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/janitor/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config as janitor_config
from . import scanner


def run(args: argparse.Namespace) -> int:
    config, config_hash = janitor_config.load_config(
        override_path=args.override if args.override else janitor_config._USE_DEFAULT_OVERRIDE
    )
    result = scanner.run_scan(
        Path(args.memory_root),
        knowledge_root=Path(args.knowledge_root) if args.knowledge_root else None,
        config=config,
        config_hash=config_hash,
        now=args.now,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0
```

Then wire into `paulshaclaw/memory/cli.py`. In `_build_parser`, after the existing `replay` parser block, add:

```python
    janitor = memory_subparsers.add_parser("janitor")
    janitor_subparsers = janitor.add_subparsers(dest="janitor_command", required=True)
    scan = janitor_subparsers.add_parser("scan")
    scan.add_argument("--memory-root", required=True)
    scan.add_argument("--knowledge-root", default=None)
    scan.add_argument("--now", default=None)
    scan.add_argument("--override", default=None)
    scan.add_argument("--dry-run", action="store_true")
    scan.set_defaults(func=_janitor_scan)
```

And add this function near the other `_*` handlers in `paulshaclaw/memory/cli.py`:

```python
def _janitor_scan(args: argparse.Namespace) -> int:
    from .janitor.cli import run as janitor_run

    return janitor_run(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_cli -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/janitor/cli.py paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_janitor_cli.py
git commit -m "feat(stage2): wire psc memory janitor scan CLI"
```

---

## Task 9: E2E fixtures + 全流程測試（reactivation 循環 / anti-flap / 安全）

**Files:**
- Create: `paulshaclaw/memory/tests/fixtures/knowledge/ttl/sl-ttl.md`
- Create: `paulshaclaw/memory/tests/fixtures/knowledge/superseded/sl-old.md`
- Create: `paulshaclaw/memory/tests/fixtures/knowledge/superseded/sl-new.md`
- Test: `paulshaclaw/memory/tests/test_janitor_e2e.py`

- [ ] **Step 1: Write the failing test**

先建 fixtures：

```markdown
<!-- paulshaclaw/memory/tests/fixtures/knowledge/ttl/sl-ttl.md -->
---
memory_layer: knowledge
slice_id: sl-ttl
project: paulshaclaw
source_agent: claude
source_session: sess-ttl
source_artifact: a.md
captured_at: "2020-01-01T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
body
```

```markdown
<!-- paulshaclaw/memory/tests/fixtures/knowledge/superseded/sl-old.md -->
---
memory_layer: knowledge
slice_id: sl-old
project: paulshaclaw
source_agent: claude
source_session: sess-old
source_artifact: a.md
captured_at: "2026-05-30T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
body
```

```markdown
<!-- paulshaclaw/memory/tests/fixtures/knowledge/superseded/sl-new.md -->
---
memory_layer: knowledge
slice_id: sl-new
supersedes:
  - sl-old
project: paulshaclaw
source_agent: claude
source_session: sess-new
source_artifact: a.md
captured_at: "2026-05-30T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
body
```

Then the test:

```python
# paulshaclaw/memory/tests/test_janitor_e2e.py
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.janitor import config as janitor_config
from paulshaclaw.memory.janitor import scanner
from paulshaclaw.memory.ledger import lifecycle, retrieval_set

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "knowledge"
PATH_OK = lambda record: True


def _cfg():
    return janitor_config.load_config(override_path=None)


def _seed_import(root: Path, key: str, status: str, ts: str) -> None:
    path = root / "runtime" / "ledger" / "import.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"idempotency_key": key, "status": status, "recorded_at": ts}) + "\n")


class JanitorE2ETests(unittest.TestCase):
    def test_scenario_a_ttl_decay(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=h,
                             now="2026-05-31T00:00:00Z", source_path_exists=PATH_OK)
            self.assertEqual(retrieval_set.active_records(root, ["sl-ttl"]), [])

    def test_scenario_b_superseded(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "superseded", kroot)
            cfg, h = _cfg()
            scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=h,
                             now="2026-05-31T00:00:00Z", source_path_exists=PATH_OK)
            decayed = [e for e in lifecycle.read_events(root) if e["record_id"] == "sl-old"]
            self.assertEqual(decayed[0]["reason"], "superseded")
            self.assertEqual(decayed[0]["detail"]["superseded_by"], "sl-new")
            self.assertEqual(retrieval_set.active_records(root, ["sl-old", "sl-new"]), ["sl-new"])

    def test_scenario_c_source_invalid(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=h,
                             now="2020-02-01T00:00:00Z",  # before TTL (captured 2020-01-01 + 90d)
                             source_path_exists=lambda record: False)
            decayed = lifecycle.read_events(root)
            self.assertEqual(decayed[0]["reason"], "source_invalid")

    def test_scenario_d_reactivation_cycle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            kwargs = dict(knowledge_root=kroot, config=cfg, config_hash=h, source_path_exists=PATH_OK)
            scanner.run_scan(root, now="2026-05-31T00:00:00Z", **kwargs)  # decays
            self.assertEqual(retrieval_set.record_state(root, "sl-ttl"), "decayed")
            _seed_import(root, "claude:sess-ttl", "updated", "2026-06-01T00:00:00Z")
            scanner.run_scan(root, now="2026-06-02T00:00:00Z", **kwargs)  # reactivates
            self.assertEqual(retrieval_set.record_state(root, "sl-ttl"), "active")
            events = lifecycle.read_events(root)
            self.assertEqual(events[-1]["event_type"], "reactivation")
            self.assertEqual(events[-1]["agent_ref"], "claude:sess-ttl")

    def test_scenario_e_idempotent(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            kwargs = dict(knowledge_root=kroot, config=cfg, config_hash=h,
                          now="2026-05-31T00:00:00Z", source_path_exists=PATH_OK)
            scanner.run_scan(root, **kwargs)
            scanner.run_scan(root, **kwargs)
            self.assertEqual(len(lifecycle.read_events(root)), 1)

    def test_scenario_f_anti_flap(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            kwargs = dict(knowledge_root=kroot, config=cfg, config_hash=h, source_path_exists=PATH_OK)
            scanner.run_scan(root, now="2026-05-31T00:00:00Z", **kwargs)
            _seed_import(root, "claude:sess-ttl", "updated", "2026-06-01T00:00:00Z")
            scanner.run_scan(root, now="2026-06-02T00:00:00Z", **kwargs)  # reactivate
            n_before = len(lifecycle.read_events(root))
            scanner.run_scan(root, now="2026-06-03T00:00:00Z", **kwargs)  # must NOT re-decay
            self.assertEqual(len(lifecycle.read_events(root)), n_before)
            self.assertEqual(retrieval_set.record_state(root, "sl-ttl"), "active")

    def test_lifecycle_ledger_has_no_record_body(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            shutil.copytree(FIXTURES / "ttl", kroot)
            cfg, h = _cfg()
            scanner.run_scan(root, knowledge_root=kroot, config=cfg, config_hash=h,
                             now="2026-05-31T00:00:00Z", source_path_exists=PATH_OK)
            raw = (root / "runtime" / "ledger" / "lifecycle.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("body", raw)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_e2e -v`
Expected: FAIL initially with `FileNotFoundError` for fixtures (create them first), then PASS after fixtures exist — if any scenario fails, fix the rule/scanner, not the test.

- [ ] **Step 3: Create fixtures**

Create the three fixture files shown in Step 1 (strip the `<!-- ... -->` comment line; that line only labels the path).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_janitor_e2e -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/tests/fixtures/knowledge paulshaclaw/memory/tests/test_janitor_e2e.py
git commit -m "test(stage2): add T4 janitor end-to-end scenarios"
```

---

## Task 10: 整合檢查 + routing.md 交叉引用 + 全套回歸

**Files:**
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`（加 janitor dry-run over fixtures）
- Modify: `paulshaclaw/memory/routing.md`（在 decayed/reactivation 段標明 T4 已落地與 ledger 路徑）

- [ ] **Step 1: Add a janitor dry-run guard to the integration check**

在 `paulshaclaw/memory/tests/stage2_integration_check.sh` 的 `echo "[stage2] ok"` 之前插入：

```bash
echo "[stage2] janitor dry-run over fixtures"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory janitor scan \
  --memory-root "$(mktemp -d)" \
  --knowledge-root "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/knowledge/ttl" \
  --now "2026-05-31T00:00:00Z" \
  --dry-run | grep -Fq '"decayed": 1'
```

- [ ] **Step 2: Run the integration check**

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: ends with `[stage2] ok`

> 注意：dry-run 用預設 `_default_source_path_exists`。fixture `sl-ttl` 的 `captured_at` 為 2020，無論 `provenance.path` 是否解析得到（TTL 或 source_invalid 皆會觸發），該記錄都會 decay，故 summary 恆為 `"decayed": 1`；斷言只檢查 count，不鎖定 reason。

- [ ] **Step 3: Update routing.md cross-reference**

在 `paulshaclaw/memory/routing.md` 的「## 3. decayed/reactivation 事件流程」段落結尾加一行：

```markdown

> **T4 已落地（2026-05）：** decayed/reactivation 事件由最小 janitor 寫入 `runtime/ledger/lifecycle.jsonl`，active 集合由 `paulshaclaw.memory.ledger.retrieval_set.active_records()` 提供。掃描入口：`psc memory janitor scan`。設計見 `docs/superpowers/specs/2026-05-31-stage2-t4-ledger-janitor-design.md`。
```

- [ ] **Step 4: Run full regression**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`
Expected: PASS（既有 + 本計畫新增測試全綠）

Run: `python3 -m unittest discover -s tests -v`
Expected: 既有唯一已知失敗 `tests/test_stage9_project_monitor.py`（worktree-layout，與本計畫無關）；無新增 T4 回歸。

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/tests/stage2_integration_check.sh paulshaclaw/memory/routing.md
git commit -m "test(stage2): wire T4 janitor into integration check and routing"
```

---

## Verification Summary（實作完成後填）

（填入：`test_janitor_*` 與 `test_lifecycle_ledger`/`test_retrieval_set`/`test_import_log` 聚焦結果、`unittest discover -s paulshaclaw/memory/tests` 全套結果、`stage2_integration_check.sh` 輸出、`unittest discover -s tests` 回歸狀態。）
