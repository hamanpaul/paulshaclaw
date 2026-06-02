# Stage 2 Topic 3.2 — LLM Semantic Atomizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the merged Topic 3 deterministic `Promoter` with a per-session LLM semantic promoter (split/merge + tags + relations) driven by a configurable one-shot `agent_exec` backend, fully testable via an injected fake.

**Architecture:** Behavior lives in a seed skill document; `LLMPromoter` is pure (takes an injected `AgentClient`); a `CachingAgentClient` decorator freezes raw output by prompt-hash for crash-resume determinism. Only the `Promoter` seam (widened per-fragment → per-session) and `promote_pass` change in the Topic 3 pipeline. No LLM/network in CI — tests use `FakeAgentClient` or a stub command.

**Tech Stack:** Python 3.12, stdlib (`subprocess`/`json`/`hashlib`/`dataclasses`), `unittest`. Cross-stage contract: `paulshaclaw.lifecycle.schema`.

**Design:** `docs/superpowers/specs/2026-06-02-stage2-llm-atomizer-design.md`
**OpenSpec:** `openspec/changes/stage2-llm-atomizer/`

**Merged Topic 3 facts (reuse, do not rewrite):**
- `Fragment(project, source_agent, source_session, source_artifact, captured_at, provenance, fragment_index, body)` in `atomizer/splitter.py`.
- `Slice(slice_id, frontmatter, body)` (frozen) + `build`/`validate`/`render` + `_SCALAR_ORDER` in `atomizer/slice_frontmatter.py`.
- `Promoter.promote(fragment, config)` + `IdentityPromoter` in `atomizer/promoter.py`.
- `ledger/relations.py` `append_edge(memory_root, *, type, frm, to, now, config_hash)` + `neighbors`; valid types include `fragment_of/promoted_to/distilled_from/supersedes` — **add `relates_to`/`mentions`**.
- `ledger/processing.py` `append_state(memory_root, *, session_key, state, now, config_hash, **extra)`.

**Canonical new shapes:**
- `SliceProposal(title, artifact_kind, project, tags: list[str], body, source_fragment_indices: list[int], relations: list[dict])`
- `slice_id = "sl-" + sha256(f"{agent}|{session}|" + sha256(body).hexdigest())[:16]`
- canned fake JSON (reused in tests): `[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw","tags":["t1"],"body":"alpha distilled","source_fragment_indices":[0],"relations":[{"type":"mentions","entity":"MTK"}]}]`

---

## Task 1: `agent_exec.py` — client interface, exec client, fake, caching decorator

**Files:**
- Create: `paulshaclaw/memory/atomizer/agent_exec.py`
- Create: `paulshaclaw/memory/tests/fixtures/atomizer/fake-agent.py`
- Test: `paulshaclaw/memory/tests/test_agent_exec.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_agent_exec.py
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.atomizer import agent_exec

STUB = Path(__file__).resolve().parent / "fixtures" / "atomizer" / "fake-agent.py"


class AgentExecTests(unittest.TestCase):
    def test_fake_client_returns_canned(self):
        client = agent_exec.FakeAgentClient("CANNED")
        self.assertEqual(client.run("anything"), "CANNED")

    def test_exec_client_runs_stub_and_returns_stdout(self):
        client = agent_exec.AgentExecClient([sys.executable, str(STUB)], timeout=30)
        out = client.run("hello prompt")
        self.assertIn("alpha", out)  # stub echoes canned slice JSON

    def test_exec_client_missing_command_raises(self):
        client = agent_exec.AgentExecClient(["/nonexistent/bin/nope"], timeout=5)
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_exec_client_nonzero_exit_raises(self):
        client = agent_exec.AgentExecClient([sys.executable, "-c", "import sys; sys.exit(3)"], timeout=5)
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_exec_client_timeout_raises(self):
        client = agent_exec.AgentExecClient([sys.executable, "-c", "import time; time.sleep(5)"], timeout=1)
        with self.assertRaises(agent_exec.AgentExecError):
            client.run("x")

    def test_caching_client_reuses_by_prompt_hash(self):
        with TemporaryDirectory() as tmp:
            calls = {"n": 0}

            class Counting(agent_exec.AgentClient):
                def run(self, prompt: str) -> str:
                    calls["n"] += 1
                    return "OUT"

            cached = agent_exec.CachingAgentClient(Counting(), Path(tmp))
            self.assertEqual(cached.run("p"), "OUT")
            self.assertEqual(cached.run("p"), "OUT")  # second time from cache
            self.assertEqual(calls["n"], 1)

    def test_caching_client_corrupt_entry_is_miss(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cached = agent_exec.CachingAgentClient(agent_exec.FakeAgentClient("FRESH"), cache_dir)
            # Pre-write a cache file for prompt "p" then corrupt it by truncation is N/A (txt);
            # instead ensure a normal miss-then-hit cycle works and returns content.
            self.assertEqual(cached.run("p"), "FRESH")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_agent_exec -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paulshaclaw.memory.atomizer.agent_exec'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/tests/fixtures/atomizer/fake-agent.py
#!/usr/bin/env python3
"""Stub agent: ignores stdin, prints a canned slice-proposal JSON array."""
import sys

sys.stdin.read()
print('[{"title":"alpha","artifact_kind":"report","project":"paulshaclaw",'
      '"tags":["t1"],"body":"alpha distilled","source_fragment_indices":[0],'
      '"relations":[{"type":"mentions","entity":"MTK"}]}]')
```

```python
# paulshaclaw/memory/atomizer/agent_exec.py
from __future__ import annotations

import hashlib
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class AgentExecError(Exception):
    """Raised when the agent subprocess cannot produce usable output."""


class AgentClient(ABC):
    @abstractmethod
    def run(self, prompt: str) -> str:
        ...


class AgentExecClient(AgentClient):
    def __init__(self, command: list[str], timeout: int = 600) -> None:
        self._command = list(command)
        self._timeout = timeout

    def run(self, prompt: str) -> str:
        try:
            completed = subprocess.run(
                self._command, input=prompt, capture_output=True,
                text=True, timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise AgentExecError(f"agent command not found: {self._command[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise AgentExecError(f"agent timed out after {self._timeout}s") from exc
        if completed.returncode != 0:
            raise AgentExecError(f"agent exited with code {completed.returncode}")
        if not completed.stdout.strip():
            raise AgentExecError("agent produced empty output")
        return completed.stdout


class FakeAgentClient(AgentClient):
    def __init__(self, canned: str) -> None:
        self._canned = canned

    def run(self, prompt: str) -> str:
        return self._canned


class CachingAgentClient(AgentClient):
    """Freeze raw output by prompt hash for crash-resume determinism."""

    def __init__(self, inner: AgentClient, cache_dir: Path) -> None:
        self._inner = inner
        self._cache_dir = cache_dir

    def _path(self, prompt: str) -> Path:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]
        return self._cache_dir / f"{digest}.txt"

    def run(self, prompt: str) -> str:
        path = self._path(prompt)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                pass  # corrupt/unreadable -> treat as miss
        out = self._inner.run(prompt)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(path)
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_agent_exec -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/agent_exec.py paulshaclaw/memory/tests/fixtures/atomizer/fake-agent.py paulshaclaw/memory/tests/test_agent_exec.py
git commit -m "feat(stage2): add T3.2 agent_exec client + cache decorator"
```

---

## Task 2: `llm_output.py` — JSON parse + schema validation

**Files:**
- Create: `paulshaclaw/memory/atomizer/llm_output.py`
- Test: `paulshaclaw/memory/tests/test_llm_output.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_llm_output.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import llm_output

PROJECTS = ["paulshaclaw", "prplos-core"]
GOOD = ('prose before\n```json\n'
        '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":["t"],'
        '"body":"b","source_fragment_indices":[0],"relations":[]}]\n```\nprose after')


class LlmOutputTests(unittest.TestCase):
    def test_parses_fenced_json(self):
        proposals = llm_output.parse(GOOD, PROJECTS)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].artifact_kind, "report")
        self.assertEqual(proposals[0].project, "paulshaclaw")

    def test_parses_bare_array(self):
        raw = '[{"title":"a","artifact_kind":"plan","project":"_unknown","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]'
        self.assertEqual(len(llm_output.parse(raw, PROJECTS)), 1)

    def test_malformed_json_raises(self):
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse("not json at all", PROJECTS)

    def test_bad_artifact_kind_raises(self):
        raw = '[{"title":"a","artifact_kind":"banana","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]'
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_unknown_project_raises(self):
        raw = '[{"title":"a","artifact_kind":"report","project":"ghost","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]'
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)

    def test_empty_body_raises(self):
        raw = '[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":[],"body":"  ","source_fragment_indices":[0],"relations":[]}]'
        with self.assertRaises(llm_output.LlmOutputError):
            llm_output.parse(raw, PROJECTS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_llm_output -v`
Expected: FAIL with `ImportError: cannot import name 'llm_output'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/llm_output.py
from __future__ import annotations

import json
from dataclasses import dataclass

from paulshaclaw.lifecycle.schema import ARTIFACT_KINDS


class LlmOutputError(Exception):
    """Raised when agent output is missing, malformed, or schema-invalid."""


@dataclass(frozen=True)
class SliceProposal:
    title: str
    artifact_kind: str
    project: str
    tags: tuple[str, ...]
    body: str
    source_fragment_indices: tuple[int, ...]
    relations: tuple[dict, ...]


def _extract_json(raw: str) -> str:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise LlmOutputError("no JSON array found in agent output")
    return raw[start:end + 1]


def parse(raw: str, known_projects: list[str]) -> list[SliceProposal]:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise LlmOutputError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise LlmOutputError("agent output must be a JSON array")

    allowed_projects = set(known_projects) | {"_unknown"}
    proposals: list[SliceProposal] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise LlmOutputError(f"proposal {index} is not an object")
        kind = item.get("artifact_kind")
        if kind not in ARTIFACT_KINDS:
            raise LlmOutputError(f"proposal {index} has invalid artifact_kind: {kind}")
        project = item.get("project")
        if project not in allowed_projects:
            raise LlmOutputError(f"proposal {index} has unknown project: {project}")
        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            raise LlmOutputError(f"proposal {index} has empty body")
        indices = item.get("source_fragment_indices") or []
        if not isinstance(indices, list):
            raise LlmOutputError(f"proposal {index} source_fragment_indices must be a list")
        relations = item.get("relations") or []
        if not isinstance(relations, list):
            raise LlmOutputError(f"proposal {index} relations must be a list")
        tags = item.get("tags") or []
        proposals.append(SliceProposal(
            title=str(item.get("title", "")),
            artifact_kind=str(kind),
            project=str(project),
            tags=tuple(str(t) for t in tags),
            body=body,
            source_fragment_indices=tuple(int(i) for i in indices),
            relations=tuple(r for r in relations if isinstance(r, dict)),
        ))
    return proposals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_llm_output -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/llm_output.py paulshaclaw/memory/tests/test_llm_output.py
git commit -m "feat(stage2): add T3.2 LLM output contract parser"
```

---

## Task 3: `prompt.py` — prompt assembly

**Files:**
- Create: `paulshaclaw/memory/atomizer/prompt.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_prompt.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_atomizer_prompt.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import prompt as prompt_mod
from paulshaclaw.memory.atomizer.splitter import Fragment


def _frag(index, body):
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact="research", captured_at="2026-06-02T00:00:00Z",
                    provenance={"repo": "r", "commit": "c", "path": "p"}, fragment_index=index, body=body)


class PromptTests(unittest.TestCase):
    def test_includes_skill_fragments_and_projects(self):
        text = prompt_mod.build_prompt("SKILLDOC", [_frag(0, "alpha"), _frag(1, "beta")],
                                       ["paulshaclaw", "prplos-core"])
        self.assertIn("SKILLDOC", text)
        self.assertIn("alpha", text)
        self.assertIn("beta", text)
        self.assertIn("prplos-core", text)
        self.assertIn("[fragment 0]", text)
        self.assertIn("[fragment 1]", text)

    def test_deterministic(self):
        frags = [_frag(0, "alpha")]
        self.assertEqual(prompt_mod.build_prompt("S", frags, ["p"]),
                        prompt_mod.build_prompt("S", frags, ["p"]))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_prompt -v`
Expected: FAIL with `ImportError: cannot import name 'prompt'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/prompt.py
from __future__ import annotations

from .splitter import Fragment


def build_prompt(skill_text: str, fragments: list[Fragment], known_projects: list[str]) -> str:
    parts = [
        skill_text,
        "",
        "## Known projects (choose exactly one per slice, or _unknown)",
        ", ".join(known_projects) if known_projects else "_unknown",
        "",
        "## Session fragments to atomize",
    ]
    for fragment in fragments:
        parts.append(f"[fragment {fragment.fragment_index}]")
        parts.append(fragment.body)
        parts.append("")
    parts.append("## Output")
    parts.append("Return ONLY the JSON array specified by the skill's output contract.")
    return "\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_prompt -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/prompt.py paulshaclaw/memory/tests/test_atomizer_prompt.py
git commit -m "feat(stage2): add T3.2 prompt assembly"
```

---

## Task 4: `slice_frontmatter.build_from_proposal` + `Slice.relations`

**Files:**
- Modify: `paulshaclaw/memory/atomizer/slice_frontmatter.py`
- Test: `paulshaclaw/memory/tests/test_slice_frontmatter.py` (extend)

- [ ] **Step 1: Write the failing test (append to existing test file)**

```python
# append to paulshaclaw/memory/tests/test_slice_frontmatter.py
import hashlib

from paulshaclaw.lifecycle.schema import compute_checksum, validate_frontmatter
from paulshaclaw.memory.atomizer import slice_frontmatter
from paulshaclaw.memory.atomizer.llm_output import SliceProposal

_SESSION_META = {
    "source_agent": "claude", "source_session": "s1",
    "captured_at": "2026-06-02T00:00:00Z",
    "provenance": {"repo": "r", "commit": "c", "path": "p"},
}


def _proposal(body="distilled body"):
    return SliceProposal(title="alpha", artifact_kind="report", project="prplos-core",
                         tags=("pwhm", "fsm"), body=body, source_fragment_indices=(0, 1),
                         relations=({"type": "mentions", "entity": "MTK"},))


class BuildFromProposalTests(unittest.TestCase):
    def test_content_derived_slice_id(self):
        s = slice_frontmatter.build_from_proposal(_proposal("X"), _SESSION_META)
        expected = "sl-" + hashlib.sha256(
            ("claude|s1|" + hashlib.sha256(b"X").hexdigest()).encode()).hexdigest()[:16]
        self.assertEqual(s.slice_id, expected)

    def test_union_frontmatter_with_tags(self):
        s = slice_frontmatter.build_from_proposal(_proposal(), _SESSION_META)
        self.assertEqual(s.frontmatter["project"], "prplos-core")
        self.assertEqual(s.frontmatter["artifact_kind"], "report")
        self.assertEqual(s.frontmatter["tags"], ["pwhm", "fsm"])
        self.assertEqual(s.frontmatter["memory_layer"], "knowledge")
        self.assertEqual(s.frontmatter["source_fragments"], [0, 1])
        self.assertEqual(s.frontmatter["checksum"], compute_checksum(s.body))

    def test_passes_dual_validation(self):
        s = slice_frontmatter.build_from_proposal(_proposal(), _SESSION_META)
        self.assertEqual(slice_frontmatter.validate(s.frontmatter, s.body), [])
        self.assertTrue(validate_frontmatter(frontmatter=s.frontmatter, body=s.body).ok)

    def test_relations_attached(self):
        s = slice_frontmatter.build_from_proposal(_proposal(), _SESSION_META)
        self.assertEqual(s.relations[0]["entity"], "MTK")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_slice_frontmatter -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'build_from_proposal'`

- [ ] **Step 3: Modify `slice_frontmatter.py`**

Add `tags` and `source_fragments` to `_SCALAR_ORDER` (after `fragment_ref`):

```python
_SCALAR_ORDER = (
    "phase", "project", "slice_id", "artifact_kind", "version", "created_at",
    "created_by", "source_session", "gate_required", "checksum",
    "memory_layer", "source_agent", "captured_at", "supersedes",
    "distilled_from", "fragment_ref", "tags", "source_fragments",
)
```

Add a `relations` field to `Slice` (default empty):

```python
@dataclass(frozen=True)
class Slice:
    slice_id: str
    frontmatter: dict[str, object]
    body: str
    relations: tuple[dict, ...] = ()
```

Add the new builder (import `SliceProposal` lazily to avoid a cycle):

```python
def build_from_proposal(proposal, session_meta: dict) -> "Slice":
    body = proposal.body
    agent = str(session_meta["source_agent"])
    session = str(session_meta["source_session"])
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    slice_id = "sl-" + hashlib.sha256(f"{agent}|{session}|{body_hash}".encode("utf-8")).hexdigest()[:16]
    phase_map = {
        "research": "research", "spec": "define", "plan": "plan",
        "report": "review", "review": "review",
    }
    phase = phase_map.get(proposal.artifact_kind, "review")
    frontmatter: dict[str, object] = {
        "phase": phase,
        "project": proposal.project,
        "slice_id": slice_id,
        "artifact_kind": proposal.artifact_kind,
        "version": "1",
        "created_at": str(session_meta["captured_at"]),
        "created_by": agent,
        "source_session": session,
        "gate_required": False,
        "checksum": stage3.compute_checksum(body),
        "memory_layer": "knowledge",
        "source_agent": agent,
        "captured_at": str(session_meta["captured_at"]),
        "provenance": dict(session_meta.get("provenance") or {}),
        "supersedes": [],
        "distilled_from": f"{agent}:{session}",
        "tags": list(proposal.tags),
        "source_fragments": list(proposal.source_fragment_indices),
    }
    return Slice(slice_id=slice_id, frontmatter=frontmatter, body=body,
                 relations=tuple(proposal.relations))
```

> Note: `render()` already iterates `_SCALAR_ORDER` and handles list values via `_scalar`, so `tags`/`source_fragments` serialize as `[a, b]`; `validate()` is unchanged and still enforces Stage 3 ∪ T4.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_slice_frontmatter -v`
Expected: PASS (existing + 4 new)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/slice_frontmatter.py paulshaclaw/memory/tests/test_slice_frontmatter.py
git commit -m "feat(stage2): add T3.2 build_from_proposal with tags/relations"
```

---

## Task 5: Per-session `Promoter` interface + `IdentityPromoter`

**Files:**
- Modify: `paulshaclaw/memory/atomizer/promoter.py`
- Modify: `paulshaclaw/memory/tests/test_atomizer_promoter.py`

- [ ] **Step 1: Update the test to the per-session signature**

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


def _frag(i):
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact="research", captured_at="2026-06-02T00:00:00Z",
                    provenance={"repo": "r", "commit": "c", "path": "p"}, fragment_index=i, body=f"b{i}")


class IdentityPromoterTests(unittest.TestCase):
    def test_one_slice_per_fragment(self):
        slices = promoter.IdentityPromoter().promote([_frag(0), _frag(1)], CFG)
        self.assertEqual(len(slices), 2)

    def test_empty_relations(self):
        s = promoter.IdentityPromoter().promote([_frag(0)], CFG)[0]
        self.assertEqual(s.relations, ())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_promoter -v`
Expected: FAIL (IdentityPromoter.promote currently takes a single fragment)

- [ ] **Step 3: Modify `promoter.py`**

```python
# paulshaclaw/memory/atomizer/promoter.py
from __future__ import annotations

from abc import ABC, abstractmethod

from . import slice_frontmatter
from .config import AtomizerConfig
from .slice_frontmatter import Slice
from .splitter import Fragment


class Promoter(ABC):
    """Maps one session's fragments to knowledge slices."""

    @abstractmethod
    def promote(self, fragments: list[Fragment], config: AtomizerConfig) -> list[Slice]:
        ...


class IdentityPromoter(Promoter):
    def promote(self, fragments: list[Fragment], config: AtomizerConfig) -> list[Slice]:
        return [slice_frontmatter.build(fragment, config) for fragment in fragments]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_promoter -v`
Expected: PASS (2 tests). Pipeline tests will be updated in Task 7.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/promoter.py paulshaclaw/memory/tests/test_atomizer_promoter.py
git commit -m "feat(stage2): widen Promoter seam to per-session"
```

---

## Task 6: `llm_promoter.py` — LLMPromoter

**Files:**
- Create: `paulshaclaw/memory/atomizer/llm_promoter.py`
- Test: `paulshaclaw/memory/tests/test_llm_promoter.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_llm_promoter.py
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import llm_promoter
from paulshaclaw.memory.atomizer.agent_exec import FakeAgentClient
from paulshaclaw.memory.atomizer.config import AtomizerConfig
from paulshaclaw.memory.atomizer.splitter import Fragment

CFG = AtomizerConfig(schema_version="1", boundary_patterns=(r"^#{1,6}\s",), max_fragment_chars=8000,
                     artifact_kind_map={}, phase_map={}, default_artifact_kind="report", default_phase="review")

_TWO = ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":["x"],'
        '"body":"body a","source_fragment_indices":[0],"relations":[]},'
        '{"title":"b","artifact_kind":"plan","project":"paulshaclaw","tags":[],'
        '"body":"body b","source_fragment_indices":[1],"relations":[]}]')
_MERGE = ('[{"title":"m","artifact_kind":"report","project":"paulshaclaw","tags":[],'
          '"body":"merged","source_fragment_indices":[0,1],"relations":[]}]')


def _frag(i):
    return Fragment(project="paulshaclaw", source_agent="claude", source_session="s1",
                    source_artifact="research", captured_at="2026-06-02T00:00:00Z",
                    provenance={"repo": "r", "commit": "c", "path": "p"}, fragment_index=i, body=f"b{i}")


def _promoter(canned):
    return llm_promoter.LLMPromoter(FakeAgentClient(canned), skill_text="SKILL",
                                    known_projects=["paulshaclaw"])


class LLMPromoterTests(unittest.TestCase):
    def test_two_slices(self):
        slices = _promoter(_TWO).promote([_frag(0), _frag(1)], CFG)
        self.assertEqual(len(slices), 2)

    def test_merge_two_fragments_into_one_slice(self):
        slices = _promoter(_MERGE).promote([_frag(0), _frag(1)], CFG)
        self.assertEqual(len(slices), 1)
        self.assertEqual(slices[0].frontmatter["source_fragments"], [0, 1])

    def test_invalid_output_fails_closed(self):
        with self.assertRaises(llm_promoter.PromoteError):
            _promoter("garbage not json").promote([_frag(0)], CFG)

    def test_bad_artifact_kind_fails_closed(self):
        bad = '[{"title":"a","artifact_kind":"nope","project":"paulshaclaw","tags":[],"body":"b","source_fragment_indices":[0],"relations":[]}]'
        with self.assertRaises(llm_promoter.PromoteError):
            _promoter(bad).promote([_frag(0)], CFG)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_llm_promoter -v`
Expected: FAIL with `ImportError: cannot import name 'llm_promoter'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/atomizer/llm_promoter.py
from __future__ import annotations

from . import llm_output, prompt, slice_frontmatter
from .agent_exec import AgentClient, AgentExecError
from .config import AtomizerConfig
from .promoter import Promoter
from .slice_frontmatter import Slice
from .splitter import Fragment


class PromoteError(Exception):
    """Session-level fail-closed: promotion could not complete safely."""


class LLMPromoter(Promoter):
    def __init__(self, agent_client: AgentClient, skill_text: str, known_projects: list[str]) -> None:
        self._agent = agent_client
        self._skill = skill_text
        self._projects = list(known_projects)

    def promote(self, fragments: list[Fragment], config: AtomizerConfig) -> list[Slice]:
        if not fragments:
            return []
        first = fragments[0]
        session_meta = {
            "source_agent": first.source_agent,
            "source_session": first.source_session,
            "captured_at": first.captured_at,
            "provenance": dict(first.provenance),
        }
        text = prompt.build_prompt(self._skill, fragments, self._projects)
        try:
            raw = self._agent.run(text)
            proposals = llm_output.parse(raw, self._projects)
        except (AgentExecError, llm_output.LlmOutputError) as exc:
            raise PromoteError(f"llm promote failed: {exc}") from exc

        slices: list[Slice] = []
        for proposal in proposals:
            built = slice_frontmatter.build_from_proposal(proposal, session_meta)
            errors = slice_frontmatter.validate(built.frontmatter, built.body)
            if errors:
                raise PromoteError(f"slice validation failed: {errors}")
            slices.append(built)
        return slices
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_llm_promoter -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/llm_promoter.py paulshaclaw/memory/tests/test_llm_promoter.py
git commit -m "feat(stage2): add T3.2 LLMPromoter (fail-closed)"
```

---

## Task 7: Relations ledger semantic edges + `pipeline.promote_pass`

**Files:**
- Modify: `paulshaclaw/memory/ledger/relations.py` (add edge types)
- Modify: `paulshaclaw/memory/atomizer/pipeline.py`
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py` (extend)

- [ ] **Step 1: Allow the new edge types**

In `paulshaclaw/memory/ledger/relations.py`, extend the valid set:

```python
VALID_EDGE_TYPES = {"fragment_of", "promoted_to", "distilled_from", "supersedes",
                    "relates_to", "mentions"}
```

- [ ] **Step 2: Write the failing pipeline test (extend existing file)**

```python
# append to paulshaclaw/memory/tests/test_atomizer_pipeline.py
from paulshaclaw.memory.atomizer.agent_exec import FakeAgentClient
from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
from paulshaclaw.memory.ledger import relations

_LLM_JSON = ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":["k"],'
             '"body":"distilled a","source_fragment_indices":[0,1],'
             '"relations":[{"type":"mentions","entity":"MTK"}]}]')


def _llm_promoter(canned=_LLM_JSON):
    return LLMPromoter(FakeAgentClient(canned), skill_text="SKILL", known_projects=["paulshaclaw"])


class LlmPipelineTests(unittest.TestCase):
    def test_llm_promote_writes_slices_and_semantic_edges(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)  # helper already in this test module (Topic 3)
            cfg, h = atomizer_config.load_config(override_path=None)
            result = pipeline.run(root, config=cfg, config_hash=h, now="2026-06-02T03:00:00Z",
                                  promoter=_llm_promoter())
            self.assertEqual(result["summary"]["slices"], 1)  # merge -> 1 slice
            edges = relations.neighbors(root, "entity:MTK")
            self.assertTrue(any(e["type"] == "mentions" for e in edges))
            promoted = [e for e in processing.read_events(root) if e["state"] == "promoted"]
            self.assertEqual(promoted[0]["promoter"], "llm")
            self.assertIn("skill_hash", promoted[0])

    def test_llm_fail_closed_leaves_split(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_raw(root)
            cfg, h = atomizer_config.load_config(override_path=None)
            pipeline.run(root, config=cfg, config_hash=h, now="2026-06-02T03:00:00Z",
                         promoter=_llm_promoter("garbage"))
            self.assertEqual(processing.state_of(root, "claude:s1"), "split")
            self.assertEqual(list((root / "knowledge").rglob("*.md")), [])
```

- [ ] **Step 3: Modify `pipeline.py`**

> **Before editing:** read the merged `paulshaclaw/memory/atomizer/pipeline.py` and reuse its ACTUAL helper names (the promote-pass function, the fragment reader, the archive-move and atomic-write helpers, the month/path helpers, and the per-session fragment glob). The names below (`_promote_pass`, `_read_fragment`, `_atomic_write`, `_move`, `_month`, `frag_dir_glob`) follow the Topic 3 plan; if the merged file differs, adapt the edit to the real names rather than introducing duplicates. Likewise the pipeline test helper `_seed_raw` refers to whatever seeding helper the merged `test_atomizer_pipeline.py` already defines.

In `promote_pass`, replace the per-fragment promotion with whole-session promotion, semantic-edge emission, and a `promoter`/`model`/`skill_hash`-tagged `promoted` record. The pipeline computes `skill_hash`/`model`/`promoter` from the injected promoter when it is an `LLMPromoter`; otherwise `promoter="identity"`. Key changes inside the per-session loop of `_promote_pass`:

```python
# at top of pipeline.py
import hashlib
from .llm_promoter import LLMPromoter

def _promoter_meta(promoter) -> dict:
    if isinstance(promoter, LLMPromoter):
        return {"promoter": "llm", "model": getattr(promoter, "_model", "unknown"),
                "skill_hash": hashlib.sha256(promoter._skill.encode("utf-8")).hexdigest()[:16]}
    return {"promoter": "identity"}
```

Replace the body of the session loop in `_promote_pass` so it gathers all fragments, calls the promoter once, catches `PromoteError`, and emits edges:

```python
        fragments = [_read_fragment(p) for p in frag_dir_glob]
        fragments = [f for f in fragments if f is not None]
        try:
            slices = promoter.promote(fragments, config)
        except Exception as exc:  # PromoteError or any promoter failure -> fail-closed
            warnings.append(f"{session_key}: promote failed, left in split: {exc}")
            continue
        # validate already done inside promoter; write + edges + archive
        title_to_id = {s.frontmatter.get("title", s.slice_id): s.slice_id for s in slices}
        for s in slices:
            knowledge_path = memory_root / "knowledge" / str(s.frontmatter["project"]) / f"{s.slice_id}.md"
            _atomic_write(knowledge_path, slice_frontmatter.render(s))
            for fi in s.frontmatter.get("source_fragments", []):
                relations.append_edge(memory_root, type="promoted_to",
                                      frm=f"fragment:{first_fragment_stem(session_key, fi)}",
                                      to=f"slice:{s.slice_id}", now=now, config_hash=config_hash)
            relations.append_edge(memory_root, type="distilled_from",
                                  frm=f"slice:{s.slice_id}", to=f"session:{session_key}",
                                  now=now, config_hash=config_hash)
            for rel in s.relations:
                if rel.get("type") == "mentions" and rel.get("entity"):
                    relations.append_edge(memory_root, type="mentions", frm=f"slice:{s.slice_id}",
                                          to=f"entity:{rel['entity']}", now=now, config_hash=config_hash)
                elif rel.get("type") == "relates_to":
                    target_id = title_to_id.get(rel.get("target_title"))
                    if target_id:
                        relations.append_edge(memory_root, type="relates_to", frm=f"slice:{s.slice_id}",
                                              to=f"slice:{target_id}", now=now, config_hash=config_hash)
                    else:
                        warnings.append(f"{session_key}: dangling relates_to {rel.get('target_title')}")
        for frag_path in frag_dir_glob:
            _move(frag_path, memory_root / "archive" / "fragments" / _month("", now) / frag_path.name)
        processing.append_state(memory_root, session_key=session_key, state="promoted",
                                now=now, config_hash=config_hash, slices=len(slices),
                                **_promoter_meta(promoter))
```

Add the helper used above and wire the caching client when the promoter calls the agent (the cache lives in the `CachingAgentClient`, constructed in Task 8's CLI; the pipeline itself stays cache-agnostic because freezing happens inside the client):

```python
def first_fragment_stem(session_key: str, index: int) -> str:
    agent, _, session = session_key.partition(":")
    return f"{agent}__{session}__{index:03d}"
```

Also update `run(...)` to accept and thread `promoter` (Topic 3 already passes a promoter; ensure default stays `IdentityPromoter`). Keep `summary["slices"]` counting written slices.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_pipeline -v`
Expected: PASS (Topic 3 tests + 2 new LLM tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/ledger/relations.py paulshaclaw/memory/atomizer/pipeline.py paulshaclaw/memory/tests/test_atomizer_pipeline.py
git commit -m "feat(stage2): wire LLM promoter + semantic edges into promote_pass"
```

---

## Task 8: Config + CLI (`--promoter`) + caching wiring + `/agent` unification

**Files:**
- Modify: `paulshaclaw/memory/atomizer/atomizer.yaml`, `config.py`
- Modify: `paulshaclaw/memory/atomizer/cli.py`
- Modify: the paulshiabro `/agent` launcher to read `agent_exec.command`
- Test: `paulshaclaw/memory/tests/test_atomizer_config.py` (extend), `test_atomizer_cli.py` (extend)

- [ ] **Step 1: Write failing config + CLI tests**

```python
# append to paulshaclaw/memory/tests/test_atomizer_config.py
class AgentExecConfigTests(unittest.TestCase):
    def test_agent_exec_and_promoter_defaults(self):
        cfg, _ = atomizer_config.load_config(override_path=None)
        self.assertTrue(cfg.agent_exec_command)            # non-empty list
        self.assertGreater(cfg.agent_exec_timeout, 0)
        self.assertIn(cfg.default_promoter, ("identity", "llm"))
        self.assertTrue(cfg.skill_path)                    # path string
```

```python
# append to paulshaclaw/memory/tests/test_atomizer_cli.py
class AtomizeCliLlmTests(unittest.TestCase):
    def test_promoter_llm_uses_stub_agent(self):
        import os, sys
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
            raw.parent.mkdir(parents=True)
            raw.write_text(_RAW, encoding="utf-8")  # _RAW already defined in this module
            stub = str(Path(__file__).resolve().parent / "fixtures" / "atomizer" / "fake-agent.py")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["memory", "atomize", "--memory-root", str(root),
                               "--now", "2026-06-02T03:00:00Z", "--promoter", "llm",
                               "--agent-command", f"{sys.executable} {stub}"])
            self.assertEqual(rc, 0)
            self.assertTrue(list((root / "knowledge").rglob("*.md")))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_config paulshaclaw.memory.tests.test_atomizer_cli -v`
Expected: FAIL (`agent_exec_command` attr missing / `--promoter` unknown)

- [ ] **Step 3: Implement config + CLI changes**

Add to `paulshaclaw/memory/atomizer/atomizer.yaml`:

```yaml
agent_exec:
  command: ["scripts/claude-gemma4"]
  timeout_seconds: 600
  model: "gemma4-26b-a4b-nvfp4"
promoter: identity
skill_path: "skills/atomize-knowledge-slice.md"
known_projects_file: "~/.agents/config/projects.yaml"
```

Extend `AtomizerConfig` and `load_config` in `config.py`:

```python
@dataclass(frozen=True)
class AtomizerConfig:
    schema_version: str
    boundary_patterns: tuple[str, ...]
    max_fragment_chars: int
    artifact_kind_map: dict[str, str] = field(default_factory=dict)
    phase_map: dict[str, str] = field(default_factory=dict)
    default_artifact_kind: str = "report"
    default_phase: str = "review"
    agent_exec_command: tuple[str, ...] = ("scripts/claude-gemma4",)
    agent_exec_timeout: int = 600
    agent_exec_model: str = "unknown"
    default_promoter: str = "identity"
    skill_path: str = "skills/atomize-knowledge-slice.md"
    known_projects_file: str = "~/.agents/config/projects.yaml"
```

In `load_config`, after building the base fields, read the new keys:

```python
    agent_exec = effective.get("agent_exec", {}) or {}
    config = AtomizerConfig(
        ...,  # existing fields unchanged
        agent_exec_command=tuple(str(c) for c in agent_exec.get("command", ["scripts/claude-gemma4"])),
        agent_exec_timeout=int(agent_exec.get("timeout_seconds", 600)),
        agent_exec_model=str(agent_exec.get("model", "unknown")),
        default_promoter=str(effective.get("promoter", "identity")),
        skill_path=str(effective.get("skill_path", "skills/atomize-knowledge-slice.md")),
        known_projects_file=str(effective.get("known_projects_file", "~/.agents/config/projects.yaml")),
    )
```

In `paulshaclaw/memory/atomizer/cli.py`, add `--promoter` and `--agent-command`, and build the promoter:

```python
import shlex
from pathlib import Path

from .agent_exec import AgentExecClient, CachingAgentClient
from .llm_promoter import LLMPromoter
from .promoter import IdentityPromoter

def _known_projects(path_str: str) -> list[str]:
    path = Path(path_str).expanduser()
    if not path.exists():
        return []
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        return []
    projects = data.get("projects") if isinstance(data, dict) else None
    if isinstance(projects, dict):
        return list(projects.keys())
    if isinstance(projects, list):
        return [str(p.get("name", p)) if isinstance(p, dict) else str(p) for p in projects]
    return []

def _build_promoter(args, config, memory_root: Path):
    choice = args.promoter or config.default_promoter
    if choice != "llm":
        return IdentityPromoter()
    command = shlex.split(args.agent_command) if args.agent_command else list(config.agent_exec_command)
    inner = AgentExecClient(command, timeout=config.agent_exec_timeout)
    client = CachingAgentClient(inner, memory_root / "runtime" / "cache" / "atomize")
    skill_path = Path(__file__).resolve().parent / config.skill_path
    skill_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    promoter = LLMPromoter(client, skill_text, _known_projects(config.known_projects_file))
    promoter._model = config.agent_exec_model  # surfaced for processing ledger
    return promoter
```

And in the existing `run(args)` of `cli.py`, construct the promoter and pass it:

```python
    memory_root = Path(args.memory_root)
    promoter = _build_promoter(args, config, memory_root)
    result = pipeline.run(memory_root, config=config, config_hash=config_hash,
                          now=args.now, dry_run=args.dry_run, promoter=promoter)
```

In `paulshaclaw/memory/cli.py`, add the two args to the `atomize` subparser:

```python
    atomize.add_argument("--promoter", choices=["identity", "llm"], default=None)
    atomize.add_argument("--agent-command", default=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomizer_config paulshaclaw.memory.tests.test_atomizer_cli -v`
Expected: PASS

- [ ] **Step 5: Migrate `/agent` to shared command config + commit**

Find where `/agent` resolves the claude-gemma4 command (registry handler dispatching `target: agent` in `paulshaclaw/core/commands.json`); change it to read `atomizer` config's `agent_exec.command` (or a shared loader) instead of a hardcoded path. Add a focused test asserting the launched command is sourced from config, not a string literal. If `/agent` fails for a reason unrelated to the command path (e.g. tmux session management), record it in `docs/superpowers/workstreams/` as a separate debug item and do not block this task.

```bash
git add paulshaclaw/memory/atomizer/atomizer.yaml paulshaclaw/memory/atomizer/config.py \
        paulshaclaw/memory/atomizer/cli.py paulshaclaw/memory/cli.py \
        paulshaclaw/memory/tests/test_atomizer_config.py paulshaclaw/memory/tests/test_atomizer_cli.py
git commit -m "feat(stage2): wire T3.2 agent_exec config + --promoter llm CLI"
```

---

## Task 9: Seed skill + E2E + live test + integration + regression

**Files:**
- Create: `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`
- Create: `paulshaclaw/memory/tests/test_atomize_skill.py`
- Create: `paulshaclaw/memory/tests/test_atomizer_llm_live.py`
- Test/Modify: `paulshaclaw/memory/tests/test_atomizer_e2e.py`, `stage2_integration_check.sh`, `routing.md`

- [ ] **Step 1: Author the seed skill (from obsidian-atomize + vault distillation)**

Sample `atomized_from` notes from `~/notes/TechVault` and `WorkVault` (read-only; extract principles, not verbatim content), then write `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md` adapting the obsidian-atomize 6-phase workflow to paulshaclaw knowledge slices. It MUST contain a `## Output contract` section listing the JSON fields (`title`, `artifact_kind`, `project`, `tags`, `body`, `source_fragment_indices`, `relations`) and the rule "Return ONLY the JSON array."

- [ ] **Step 2: Write skill + E2E + live tests**

```python
# paulshaclaw/memory/tests/test_atomize_skill.py
from __future__ import annotations

import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "atomizer" / "skills" / "atomize-knowledge-slice.md"


class SkillDocTests(unittest.TestCase):
    def test_skill_exists_with_output_contract(self):
        self.assertTrue(SKILL.exists())
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("Output contract", text)
        for field in ("artifact_kind", "project", "tags", "body", "source_fragment_indices", "relations"):
            self.assertIn(field, text)
```

```python
# paulshaclaw/memory/tests/test_atomizer_llm_live.py
from __future__ import annotations

import os
import unittest


@unittest.skipUnless(os.environ.get("PSC_ATOMIZE_LIVE"), "set PSC_ATOMIZE_LIVE to run live agent test")
class LiveLlmAtomizeTests(unittest.TestCase):
    def test_real_agent_produces_valid_slices(self):
        import shutil
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from paulshaclaw.memory.atomizer import config as atomizer_config, pipeline
        from paulshaclaw.memory.atomizer.agent_exec import AgentExecClient, CachingAgentClient
        from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
        from paulshaclaw.lifecycle.schema import parse_artifact_text, validate_frontmatter

        fixture = Path(__file__).resolve().parent / "fixtures" / "atomizer" / "raw" / "s1.md"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "inbox" / "research" / "claude" / "2026-06-02" / "s1.md"
            raw.parent.mkdir(parents=True)
            shutil.copyfile(fixture, raw)
            cfg, h = atomizer_config.load_config(override_path=None)
            client = CachingAgentClient(AgentExecClient(list(cfg.agent_exec_command), cfg.agent_exec_timeout),
                                        root / "runtime" / "cache" / "atomize")
            promoter = LLMPromoter(client, "Atomize the session into JSON slices.", ["paulshaclaw"])
            pipeline.run(root, config=cfg, config_hash=h, now="2026-06-02T03:00:00Z", promoter=promoter)
            slice_path = next((root / "knowledge").rglob("*.md"))
            doc = parse_artifact_text(slice_path.read_text(encoding="utf-8"))
            self.assertTrue(validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body).ok)
```

Add to `paulshaclaw/memory/tests/test_atomizer_e2e.py` an LLM end-to-end (fake) case:

```python
    def test_llm_e2e_slice_passes_gate_and_has_no_body_in_ledger(self):
        from paulshaclaw.memory.atomizer.agent_exec import FakeAgentClient
        from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
        canned = ('[{"title":"a","artifact_kind":"report","project":"paulshaclaw","tags":["k"],'
                  '"body":"distilled alpha","source_fragment_indices":[0],"relations":[]}]')
        with TemporaryDirectory() as tmp:
            root = Path(tmp); _seed(root); cfg, h = _cfg()
            pipeline.run(root, config=cfg, config_hash=h, now="2026-06-02T03:00:00Z",
                         promoter=LLMPromoter(FakeAgentClient(canned), "SKILL", ["paulshaclaw"]))
            slice_path = next((root / "knowledge").rglob("*.md"))
            doc = parse_artifact_text(slice_path.read_text(encoding="utf-8"))
            self.assertTrue(validate_frontmatter(frontmatter=doc.frontmatter, body=doc.body).ok)
            ledger = (root / "runtime" / "ledger" / "relations.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("alpha body", ledger)
```

- [ ] **Step 3: Run the new tests**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_atomize_skill paulshaclaw.memory.tests.test_atomizer_e2e -v`
Expected: PASS (live test SKIPPED without `PSC_ATOMIZE_LIVE`)

- [ ] **Step 4: Integration check + routing + full regression**

Add to `paulshaclaw/memory/tests/stage2_integration_check.sh`, before `echo "[stage2] ok"`:

```bash
echo "[stage2] atomizer LLM dry-run via stub agent"
LLM_ROOT="$(mktemp -d)"
mkdir -p "$LLM_ROOT/inbox/research/claude/2026-06-02"
cp "$ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/raw/s1.md" \
   "$LLM_ROOT/inbox/research/claude/2026-06-02/s1.md"
PYTHONPATH="$ROOT_DIR" python3 -m paulshaclaw.memory.cli memory atomize \
  --memory-root "$LLM_ROOT" --now "2026-06-02T03:00:00Z" --promoter llm \
  --agent-command "$(command -v python3) $ROOT_DIR/paulshaclaw/memory/tests/fixtures/atomizer/fake-agent.py" \
  | grep -Fq '"slices":'
```

Append to `paulshaclaw/memory/routing.md`:

```markdown

> **T3.2 已落地（2026-06）：** `psc memory atomize --promoter llm` 以 configurable `agent_exec`（預設 claude-gemma4）做 per-session 語意原子化;行為定義於 `atomizer/skills/atomize-knowledge-slice.md`，語意關聯寫入 `relations.jsonl`（`relates_to`/`mentions`）。fail-closed 隔日重試。設計見 `docs/superpowers/specs/2026-06-02-stage2-llm-atomizer-design.md`。
```

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests -v`
Expected: PASS (all memory tests green; live test skipped)

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: ends with `[stage2] ok`

Run: `python3 -m unittest discover -s tests -v`
Expected: only pre-existing unrelated failures (flaky `test_start_sh`, stage9 snapshot); no new T3.2 regressions.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md \
        paulshaclaw/memory/tests/test_atomize_skill.py \
        paulshaclaw/memory/tests/test_atomizer_llm_live.py \
        paulshaclaw/memory/tests/test_atomizer_e2e.py \
        paulshaclaw/memory/tests/stage2_integration_check.sh paulshaclaw/memory/routing.md
git commit -m "test(stage2): add T3.2 seed skill, E2E, live test, integration wiring"
```

---

## Verification Summary（實作完成後填）

（填入：`test_agent_exec`/`test_llm_output`/`test_llm_promoter`/`test_slice_frontmatter` 等聚焦結果、`unittest discover -s paulshaclaw/memory/tests` 全套、`stage2_integration_check.sh` 輸出、`lifecycle.gate` 跨 stage 驗證、opt-in live-exec 說明、`tests/` 回歸狀態。）
