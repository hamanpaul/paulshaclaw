# Stage 2 Phase 2a — LLM Promoter Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the LLM atomic-distillation promoter as a forward-only canary — raise the atomize output-token window, persist atom/session titles for hierarchical MOC, render a two-layer MOC, then flip the dream loop to `--promoter llm`.

**Architecture:** The whole LLM pipeline already exists (`LLMPromoter`, `agent_exec`, seed skill, `cli._build_promoter`). This change (a) lets `AgentExecClient` carry an env override so atomize raises `CLAUDE_CODE_MAX_OUTPUT_TOKENS` past `claude-gemma4`'s 1024 default, (b) persists `session_title` + `atom_title` onto LLM atom frontmatter, (c) regroups the MOC by `source_session` into a session-spine→atom hierarchy that tolerates a mixed identity/llm layer, then (d) flips `scripts/start.sh:195`. Full backfill re-distillation is deferred to a separate Phase 2b change.

**Tech Stack:** Python 3.12, `unittest`, OpenSpec, local gemma4 via `scripts/claude-gemma4`.

---

### Task 1: AgentExecClient env override

**Files:**
- Modify: `paulshaclaw/memory/atomizer/agent_exec.py`
- Test: `paulshaclaw/memory/tests/test_agent_exec.py`

- [ ] **Step 1: Write the failing tests**

Add to `AgentExecTests` in `test_agent_exec.py`:

```python
    def test_exec_client_env_override_passed_to_subprocess(self):
        client = agent_exec.AgentExecClient(
            [sys.executable, "-c",
             "import os,sys; sys.stdin.read(); print(os.environ.get('CLAUDE_CODE_MAX_OUTPUT_TOKENS',''))"],
            timeout=5,
            env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "8192"},
        )
        self.assertEqual(client.run("x").strip(), "8192")

    def test_exec_client_no_env_inherits_parent(self):
        os.environ["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = "4242"
        self.addCleanup(os.environ.pop, "CLAUDE_CODE_MAX_OUTPUT_TOKENS", None)
        client = agent_exec.AgentExecClient(
            [sys.executable, "-c",
             "import os,sys; sys.stdin.read(); print(os.environ.get('CLAUDE_CODE_MAX_OUTPUT_TOKENS',''))"],
            timeout=5,
        )
        self.assertEqual(client.run("x").strip(), "4242")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest paulshaclaw/memory/tests/test_agent_exec.py -k env -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'env'`

- [ ] **Step 3: Implement the env parameter**

In `agent_exec.py`, add `import os` at top, then:

```python
class AgentExecClient(AgentClient):
    def __init__(self, command: list[str], timeout: int = 600, env: dict | None = None) -> None:
        self._command = list(command)
        self._timeout = timeout
        self._env = dict(env) if env is not None else None

    def run(self, prompt: str) -> str:
        if not self._command:
            raise AgentExecError("agent command not configured")
        try:
            completed = subprocess.run(
                self._command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
                env=None if self._env is None else {**os.environ, **self._env},
            )
```

(Leave the rest of `run` unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest paulshaclaw/memory/tests/test_agent_exec.py -v`
Expected: PASS (all, including the existing ones)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/agent_exec.py paulshaclaw/memory/tests/test_agent_exec.py
git commit -m "feat(stage2): AgentExecClient 支援 env override（atomize 輸出窗）"
```

---

### Task 2: Config `agent_exec.max_output_tokens`

**Files:**
- Modify: `paulshaclaw/memory/atomizer/config.py`, `paulshaclaw/memory/atomizer/atomizer.yaml`
- Test: `paulshaclaw/memory/tests/test_atomizer_config.py`

- [ ] **Step 1: Write the failing test**

Add to `test_atomizer_config.py` (use the existing temp-config helper style; minimal self-contained version below):

```python
    def test_max_output_tokens_default_and_in_hash(self):
        import tempfile, pathlib
        from paulshaclaw.memory.atomizer import config as cfgmod
        base = "schema_version: 1\nsplit:\n  boundary_patterns:\n    - '^#'\n  max_fragment_chars: 8000\n"
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p / "atomizer.yaml").write_text(base, encoding="utf-8")
            cfg_default, hash_default = cfgmod.load_config(default_dir=p, override_path=None)
            self.assertEqual(cfg_default.agent_exec_max_output_tokens, 8192)
            (p / "atomizer.yaml").write_text(base + "agent_exec:\n  max_output_tokens: 16384\n", encoding="utf-8")
            cfg_big, hash_big = cfgmod.load_config(default_dir=p, override_path=None)
            self.assertEqual(cfg_big.agent_exec_max_output_tokens, 16384)
            self.assertNotEqual(hash_default, hash_big)

    def test_max_output_tokens_rejects_non_positive(self):
        import tempfile, pathlib
        from paulshaclaw.memory.atomizer import config as cfgmod
        base = ("schema_version: 1\nsplit:\n  boundary_patterns:\n    - '^#'\n"
                "  max_fragment_chars: 8000\nagent_exec:\n  max_output_tokens: 0\n")
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p / "atomizer.yaml").write_text(base, encoding="utf-8")
            with self.assertRaises(cfgmod.AtomizerConfigError):
                cfgmod.load_config(default_dir=p, override_path=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest paulshaclaw/memory/tests/test_atomizer_config.py -k max_output -v`
Expected: FAIL — `AttributeError: 'AtomizerConfig' object has no attribute 'agent_exec_max_output_tokens'`

- [ ] **Step 3: Implement the field**

In `config.py`, add to the `AtomizerConfig` dataclass (after `agent_exec_model`):

```python
    agent_exec_max_output_tokens: int = 8192
```

In `load_config`, after the `agent_exec_model = _require_non_empty_string(...)` block:

```python
    agent_exec_max_output_tokens = _parse_positive_int(
        agent_exec_config.get("max_output_tokens", 8192),
        "agent_exec.max_output_tokens",
    )
```

And pass it into the `AtomizerConfig(...)` constructor:

```python
        agent_exec_max_output_tokens=agent_exec_max_output_tokens,
```

In `atomizer.yaml`, under `agent_exec:` add:

```yaml
  max_output_tokens: 8192
```

(config_hash hashes `config_data`, which now includes the new key — no extra wiring needed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest paulshaclaw/memory/tests/test_atomizer_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/config.py paulshaclaw/memory/atomizer/atomizer.yaml paulshaclaw/memory/tests/test_atomizer_config.py
git commit -m "feat(stage2): atomizer config 加 agent_exec.max_output_tokens（預設 8192）"
```

---

### Task 3: CLI wires the output window into the LLM client

**Files:**
- Modify: `paulshaclaw/memory/atomizer/cli.py:82` (the `AgentExecClient(...)` in `_build_promoter`)
- Test: `paulshaclaw/memory/tests/test_atomizer_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `test_atomizer_cli.py`:

```python
    def test_build_promoter_llm_sets_output_token_env(self):
        import argparse
        from pathlib import Path
        from paulshaclaw.memory.atomizer import cli, config as cfgmod
        cfg, _ = cfgmod.load_config()  # package default → 8192
        args = argparse.Namespace(promoter="llm", agent_command=None)
        promoter = cli._build_promoter(args, cfg, Path("/tmp/does-not-matter"))
        inner = promoter._agent._inner  # LLMPromoter -> CachingAgentClient -> AgentExecClient
        self.assertEqual(inner._env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"], str(cfg.agent_exec_max_output_tokens))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest paulshaclaw/memory/tests/test_atomizer_cli.py -k output_token_env -v`
Expected: FAIL — `KeyError: 'CLAUDE_CODE_MAX_OUTPUT_TOKENS'` (env is `None`)

- [ ] **Step 3: Implement the wiring**

In `cli.py:_build_promoter`, change the `AgentExecClient(...)` construction:

```python
    inner = AgentExecClient(
        command,
        timeout=config.agent_exec_timeout,
        env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config.agent_exec_max_output_tokens)},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest paulshaclaw/memory/tests/test_atomizer_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/cli.py paulshaclaw/memory/tests/test_atomizer_cli.py
git commit -m "feat(stage2): _build_promoter 把 max_output_tokens 帶進 atomize 子程序 env"
```

---

### Task 4: Persist `session_title` + `atom_title` on LLM atom frontmatter

**Files:**
- Modify: `paulshaclaw/memory/atomizer/llm_promoter.py:93-98` (session_meta dict), `paulshaclaw/memory/atomizer/slice_frontmatter.py` (`build_from_proposal`, `_SCALAR_ORDER`, `render`)
- Test: `paulshaclaw/memory/tests/test_slice_frontmatter.py` (new)

- [ ] **Step 1: Write the failing test**

Create `paulshaclaw/memory/tests/test_slice_frontmatter.py`:

```python
from __future__ import annotations

import unittest

from paulshaclaw.memory.atomizer import slice_frontmatter
from paulshaclaw.memory.atomizer.llm_output import SliceProposal


class BuildFromProposalTitleTests(unittest.TestCase):
    def _proposal(self) -> SliceProposal:
        return SliceProposal(
            title="atom one",
            artifact_kind="report",
            project="paulshaclaw",
            tags=("t1",),
            body="distilled body",
            source_fragment_indices=(0,),
            relations=(),
        )

    def _meta(self) -> dict:
        return {
            "source_agent": "claude",
            "source_session": "s1",
            "captured_at": "2026-01-01T00:00:00Z",
            "provenance": {},
            "session_title": "修正 X 啟動",
        }

    def test_titles_persisted_to_frontmatter(self):
        sl = slice_frontmatter.build_from_proposal(self._proposal(), self._meta())
        self.assertEqual(sl.frontmatter["session_title"], "修正 X 啟動")
        self.assertEqual(sl.frontmatter["atom_title"], "atom one")

    def test_titles_rendered_quoted(self):
        rendered = slice_frontmatter.render(
            slice_frontmatter.build_from_proposal(self._proposal(), self._meta())
        )
        self.assertIn('session_title: "修正 X 啟動"', rendered)
        self.assertIn('atom_title: "atom one"', rendered)

    def test_missing_session_title_defaults_empty(self):
        meta = self._meta()
        del meta["session_title"]
        sl = slice_frontmatter.build_from_proposal(self._proposal(), meta)
        self.assertEqual(sl.frontmatter["session_title"], "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest paulshaclaw/memory/tests/test_slice_frontmatter.py -v`
Expected: FAIL — `KeyError: 'atom_title'` (and `session_title` absent)

- [ ] **Step 3: Implement the plumbing**

In `llm_promoter.py`, extend the `session_meta` dict (around line 93) to carry the session title from the first fragment:

```python
        session_meta = {
            "source_agent": first.source_agent,
            "source_session": first.source_session,
            "captured_at": first.captured_at,
            "provenance": dict(first.provenance),
            "session_title": first.session_title,
        }
```

In `slice_frontmatter.py` `build_from_proposal`, add two keys to the `frontmatter` dict (after `"distilled_from"`):

```python
        "session_title": str(session_meta.get("session_title", "")),
        "atom_title": proposal.title,
```

In `_SCALAR_ORDER`, add `"atom_title"` next to `"session_title"`:

```python
    "distilled_from", "fragment_ref", "session_title", "atom_title", "tags", "source_fragments",
```

In `render`, extend the free-text-quoting branch so `atom_title` is quoted like `session_title`:

```python
        if key in ("session_title", "atom_title"):
            # free-text → always a quoted scalar so YAML indicator chars can't deform it
            lines.append(f"{key}: {json.dumps(str(fm[key]), ensure_ascii=False)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest paulshaclaw/memory/tests/test_slice_frontmatter.py paulshaclaw/memory/tests/test_llm_promoter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/atomizer/llm_promoter.py paulshaclaw/memory/atomizer/slice_frontmatter.py paulshaclaw/memory/tests/test_slice_frontmatter.py
git commit -m "feat(stage2): LLM 原子 frontmatter 補 session_title + atom_title"
```

---

### Task 5: Two-layer MOC rendering

**Files:**
- Modify: `paulshaclaw/memory/moc/moc_builder.py` (`_active_slices`, `build_mocs`, add `_hierarchy_lines`)
- Test: `paulshaclaw/memory/tests/test_moc_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `test_moc_builder.py` (extend the `_slice` helper to accept session/title fields, then assert hierarchy):

```python
def _slice_full(root: Path, slice_id: str, project: str, source_session: str,
                session_title: str, atom_title: str) -> None:
    path = root / "knowledge" / project / f"{atom_title}--{slice_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nslice_id: {slice_id}\nmemory_layer: knowledge\nproject: {project}\n"
        f"artifact_kind: report\nsource_session: {source_session}\n"
        f'session_title: "{session_title}"\natom_title: "{atom_title}"\n---\nbody {slice_id}\n',
        encoding="utf-8")


class MocTwoLayerTests(unittest.TestCase):
    def test_atoms_nested_under_session_title(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice_full(root, "sl-a1", "prplos-core", "claude:s1", "修正啟動鏈", "OOM 風險")
            _slice_full(root, "sl-a2", "prplos-core", "claude:s1", "修正啟動鏈", "PYTHONPATH 修法")
            moc_builder.build_mocs(root, now="2026-06-17T00:00:00Z")
            moc = (root / "knowledge" / "prplos-core-moc.md").read_text(encoding="utf-8")
            self.assertIn("- 修正啟動鏈", moc)               # session spine
            self.assertIn("  - [[OOM 風險--sl-a1|OOM 風險]]", moc)   # nested atom
            self.assertIn("  - [[PYTHONPATH 修法--sl-a2|PYTHONPATH 修法]]", moc)

    def test_missing_session_title_renders_flat_entry(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # no session_title / atom_title → degrade to basename, no crash
            _slice(root, "sl-x", "p", "alpha")
            moc_builder.build_mocs(root, now="2026-06-17T00:00:00Z")
            moc = (root / "knowledge" / "p-moc.md").read_text(encoding="utf-8")
            self.assertIn("alpha--sl-x", moc)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest paulshaclaw/memory/tests/test_moc_builder.py -k TwoLayer -v`
Expected: FAIL — assertion error: `- 修正啟動鏈` not found (current builder renders flat).

- [ ] **Step 3: Implement the hierarchy**

In `moc_builder.py`, make `_active_slices` read `atom_title` (extend the row to a 7-tuple). Change the candidate append to:

```python
            candidates.append((str(sid), str(fm.get("project", "_unknown")), path.stem,
                               str(fm.get("artifact_kind", "")),
                               str(fm.get("source_session", "")), str(fm.get("session_title", "")),
                               str(fm.get("atom_title", ""))))
```

(Update the function's return type hint tuples to 7 elements.)

Add a helper and use it for each MOC body:

```python
def _hierarchy_lines(rows: list[tuple]) -> list[str]:
    """Group rows by source_session into a session-title spine with nested atoms.
    Row = (slice_id, project, basename, kind, source_session, session_title, atom_title)."""
    by_session: dict[str, list[tuple]] = defaultdict(list)
    order: list[str] = []
    for row in sorted(rows, key=lambda r: (r[4], r[2])):
        sess = row[4]
        if sess not in by_session:
            order.append(sess)
        by_session[sess].append(row)
    lines: list[str] = []
    for sess in order:
        group = by_session[sess]
        parent = group[0][5] or group[0][2]          # session_title or basename
        lines.append(f"- {parent}")
        for sid, project, basename, kind, ss, st, at in group:
            label = at or st or basename             # atom_title > session_title > basename
            lines.append(f"  - [[{alias_link(basename, label)}]] — {kind}")
    return lines
```

Rewrite the three MOC bodies in `build_mocs` to use it:

```python
    for project, items in by_project.items():
        if project == "common-sense":
            continue
        lines = _hierarchy_lines(items)
        _write_moc(knowledge / f"{sanitize_project_component(project)}-moc.md", "project", now, f"{project} MOC", lines, project)

    cs_rows = [r for r in rows if r[1] == "common-sense"]
    _write_moc(knowledge / "common-sense-moc.md", "common-sense", now, "Common-sense MOC", _hierarchy_lines(cs_rows))

    active_lines = ["## Active", ""] + _hierarchy_lines(rows)
    _write_moc(knowledge / "wiki-moc.md", "wiki", now, "Wiki MOC", active_lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest paulshaclaw/memory/tests/test_moc_builder.py paulshaclaw/memory/tests/test_moc_e2e.py -v`
Expected: PASS (update any existing flat-format assertions in `test_moc_builder.py` that expected a top-level `- [[...]]` line to expect the nested `  - [[...]]` form — adjust them in this step.)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/moc/moc_builder.py paulshaclaw/memory/tests/test_moc_builder.py
git commit -m "feat(stage2): MOC 雙層階層（session 標題主脊 + 巢狀原子）"
```

---

### Task 6: End-to-end + fail-closed regression (verification, no new production code)

**Files:**
- Test: `paulshaclaw/memory/tests/test_atomizer_pipeline.py` (or `test_atomizer_e2e.py`)

- [ ] **Step 1: Add an integration test driving the LLM promoter with a fake client**

```python
    def test_llm_promote_writes_atoms_with_titles(self):
        # Arrange a single split session fragment in memory_root, then:
        from paulshaclaw.memory.atomizer.agent_exec import FakeAgentClient
        from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
        fake = FakeAgentClient(
            '[{"title":"atom one","artifact_kind":"report","project":"paulshaclaw",'
            '"tags":["t"],"body":"distilled","source_fragment_indices":[0],"relations":[]}]'
        )
        promoter = LLMPromoter(fake, skill_text="", known_projects=["paulshaclaw"], model="fake")
        result = pipeline.run(memory_root, config=cfg, config_hash="h", now=NOW, promoter=promoter)
        # Assert: a knowledge slice exists whose frontmatter has session_title + atom_title,
        # processing ledger records promoter="llm" + model + skill_hash.
```

- [ ] **Step 2: Run it**

Run: `python -m pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -k llm_promote_writes_atoms -v`
Expected: PASS (relies only on Tasks 4 changes; LLMPromoter itself unchanged).

- [ ] **Step 3: Run the full suite for real**

Run: `python -m unittest discover -s paulshaclaw/memory/tests -v && python -m pytest tests/ -q`
Expected: all PASS. Capture the summary line as evidence.

- [ ] **Step 4: Commit**

```bash
git add paulshaclaw/memory/tests/test_atomizer_pipeline.py
git commit -m "test(stage2): LLM promote 端到端（含 frontmatter 標題）+ fail-closed 回歸"
```

---

### Task 7: Flip the dream loop to `--promoter llm` (canary enablement)

**Files:**
- Modify: `scripts/start.sh:195`
- Modify (if `code_paths` changed): `README.md` / `docs/**` per R-18

- [ ] **Step 1: Flip the switch**

In `scripts/start.sh`, the dream loop invocation:

```bash
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run \
        --memory-root "$dream_root" --require-idle --promoter llm \
        >>"$dream_log" 2>&1 || true
```

(Change `--promoter identity` → `--promoter llm`. Leave `--require-idle` and the rest intact.)

- [ ] **Step 2: Sanity-check the launcher parses**

Run: `bash -n scripts/start.sh`
Expected: no syntax error (exit 0).

- [ ] **Step 3: Docs alignment (R-18)**

If any README/docs section documents the dream promoter mode, update it; otherwise this change is internal — note in the PR body that `policy-exempt:docs-sync` may apply.

- [ ] **Step 4: Commit**

```bash
git add scripts/start.sh
git commit -m "feat(stage2): dream loop 翻 --promoter llm（forward-only canary 啟用）"
```

---

## Self-Review

- **Spec coverage:**
  - *Per-session LLM atomic distillation* → existing `LLMPromoter`, exercised by Task 6.
  - *Bounded distillation output window* → Tasks 1–3.
  - *Fail-closed distillation* → existing behavior, regression in Task 6.
  - *Forward-only canary rollout* → Task 7 (switch) + Task 5 hybrid tolerance (`test_missing_session_title_renders_flat_entry`).
  - *Two-layer MOC rendering* → Tasks 4–5.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** `agent_exec_max_output_tokens` (config field) used verbatim in Tasks 2–3; `session_title`/`atom_title` frontmatter keys consistent across Tasks 4–5; `_hierarchy_lines` 7-tuple matches `_active_slices` row shape.

## Notes for the implementer

- Existing `test_moc_builder.py` flat-format assertions (`[[alpha--sl-1]]` at top level) must move under the nested form or the session-spine line in Task 5 Step 4 — adjust, don't delete coverage.
- gemma4 path at runtime is `scripts/claude-gemma4` → proxy `:18080` → 192.0.2.10; tests never hit it (FakeAgentClient / stub only). `test_atomizer_llm_live.py` stays opt-in.
- Phase 2b (full backfill re-distillation + janitor decay) is a **separate future change**, gated on human canary judgement — do not implement it here.
