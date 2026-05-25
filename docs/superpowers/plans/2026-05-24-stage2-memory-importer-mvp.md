# Stage 2 Memory Importer MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stage 2 Topic 1 memory substrate and importer MVP for CLI session ingestion into `~/.agents/memory`.

**Architecture:** Add a focused `paulshaclaw.memory.importer` package with adapters, deterministic frontmatter rendering, idempotent pipeline writes, project resolution, classifier routing, and thin hook entrypoints. Keep runtime state under configurable memory roots for tests; repository files only provide code, tests, templates, and docs.

**Tech Stack:** Python standard library (`unittest`, `json`, `hashlib`, `fcntl`, `pathlib`, `argparse`, `tempfile`, `shutil`), optional PyYAML avoided for deterministic repo-local behavior.

---

## Chunk 1: Repo-local memory substrate, frontmatter, adapters, pipeline

### File Structure

- Create `paulshaclaw/memory/importer/__init__.py`: package exports and version boundary.
- Create `paulshaclaw/memory/importer/adapters/base.py`: spec-aligned `NormalizedSession`, canonical hash, completeness tuple, shared extraction helpers.
- Create `paulshaclaw/memory/importer/adapters/claude.py`: Claude SessionEnd JSON adapter.
- Create `paulshaclaw/memory/importer/adapters/codex.py`: Codex Stop/SubagentStop adapter.
- Create `paulshaclaw/memory/importer/adapters/copilot.py`: Copilot sessionEnd camelCase adapter.
- Create `paulshaclaw/memory/importer/frontmatter.py`: deterministic frontmatter and Markdown body rendering.
- Create `paulshaclaw/memory/importer/classifier.py`: rule-based inbox bucket selection.
- Create `paulshaclaw/memory/importer/config.py`: memory root and template config helpers.
- Create `paulshaclaw/memory/importer/pipeline.py`: queue ingestion, locking, ledger, inbox/archive writes.
- Create `paulshaclaw/memory/importer/cli.py`: `ingest --queue-item <path> [--dry-run]`.
- Create `paulshaclaw/memory/lint/frontmatter_lint.py`: frontmatter validator CLI/library.
- Create `paulshaclaw/memory/hooks/install.sh`: `--tree-only` scaffold first, full install later.
- Create fixture directories under `paulshaclaw/memory/tests/fixtures/{claude,codex,copilot}/`.
- Create tests under `paulshaclaw/memory/tests/`.

### Task 1: Memory tree and frontmatter lint

**Files:**
- Create: `paulshaclaw/memory/tests/test_tree_skeleton.py`
- Create: `paulshaclaw/memory/tests/test_frontmatter_lint.py`
- Create: `paulshaclaw/memory/hooks/install.sh`
- Create: `paulshaclaw/memory/lint/frontmatter_lint.py`

- [ ] **Step 1: Write failing tree skeleton test**

```python
def test_tree_only_install_creates_private_memory_tree(self):
    root = Path(self.tmp.name) / "memory"
    completed = subprocess.run(
        ["bash", "paulshaclaw/memory/hooks/install.sh", "--tree-only", "--memory-root", str(root)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    self.assertEqual(completed.returncode, 0, msg=completed.stderr)
    for relative in [
        "inbox", "work-centric", "knowledge", "runtime", "log", "hooks", "archive",
        "inbox/sessions", "inbox/plans", "inbox/research", "inbox/reports",
        "work-centric/common-sense", "runtime/queue", "runtime/queue/_failed",
        "runtime/locks", "runtime/ledger", "runtime/indexes", "archive/queue",
    ]:
        path = root / relative
        self.assertTrue(path.is_dir(), relative)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertTrue((path / ".gitkeep").exists())
```

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_tree_skeleton -v`
Expected: FAIL because `install.sh` does not exist or lacks `--tree-only`.

- [ ] **Step 3: Implement tree-only install**

Implement `install.sh` with `set -euo pipefail`, parse `--tree-only` and `--memory-root`, create all 7 top-level directories (`inbox`, `work-centric`, `knowledge`, `runtime`, `log`, `hooks`, `archive`) plus the nested bucket/runtime/archive directories with `install -d -m 700`, and touch `.gitkeep`.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_tree_skeleton -v`
Expected: PASS.

- [ ] **Step 5: Write failing frontmatter lint test**

```python
def test_lint_accepts_required_stage2_frontmatter(self):
    doc = self.write_doc("""---
memory_layer: inbox
project: paulshaclaw
source_agent: copilot-cli
source_session: abc-123
source_artifact: session
captured_at: 2026-05-24T00:00:00+00:00
provenance:
  repo: hamanpaul/paulshaclaw
  commit: e300b08
  path: tests/session.json
---
body
""")
    self.assertEqual(validate_file(doc), [])
```

- [ ] **Step 6: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_frontmatter_lint -v`
Expected: FAIL because lint module does not exist.

- [ ] **Step 7: Implement frontmatter lint**

Required fields: `memory_layer`, `project`, `source_agent`, `source_session`, `source_artifact`, `captured_at`, and nested `provenance.repo`, `provenance.commit`, `provenance.path`. Return explicit error strings; CLI exits 1 on validation failures.

- [ ] **Step 8: Run GREEN and commit**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_tree_skeleton paulshaclaw.memory.tests.test_frontmatter_lint -v`
Expected: PASS.

Commit:
```bash
git add paulshaclaw/memory/hooks/install.sh paulshaclaw/memory/lint/frontmatter_lint.py paulshaclaw/memory/tests/test_tree_skeleton.py paulshaclaw/memory/tests/test_frontmatter_lint.py
git commit -m "feat(stage2): scaffold memory tree and frontmatter lint"
```

### Task 2: Adapters and deterministic frontmatter rendering

**Files:**
- Create: `paulshaclaw/memory/tests/fixtures/claude/{session_end,minimal,with_artifacts}/payload.json`
- Create: `paulshaclaw/memory/tests/fixtures/codex/{stop,subagent_stop,minimal}/payload.json`
- Create: `paulshaclaw/memory/tests/fixtures/copilot/{session_end,minimal,with_history}/payload.json`
- Create: `paulshaclaw/memory/tests/test_adapters.py`
- Create: `paulshaclaw/memory/tests/test_frontmatter.py`
- Create: `paulshaclaw/memory/importer/adapters/base.py`
- Create: `paulshaclaw/memory/importer/adapters/claude.py`
- Create: `paulshaclaw/memory/importer/adapters/codex.py`
- Create: `paulshaclaw/memory/importer/adapters/copilot.py`
- Create: `paulshaclaw/memory/importer/frontmatter.py`

- [ ] **Step 1: Write failing adapter tests**

Create at least 3 sanitized fixtures per CLI. Test each adapter returns the spec-aligned `NormalizedSession` shape from the design doc: `session_id`, `tool`, `started_at`, `ended_at`, `cwd`, `repo`, `commit`, `turn_count`, `user_prompts`, `assistant_summary`, `touched_files`, `referenced_artifacts`, and `raw_payload_pointer`. Also test queue metadata fields consumed by idempotency but not part of the TypedDict contract: `capture_scope` and the raw queue payload. Include a Copilot fixture proving official `sessionId` camelCase becomes normalized `session_id`, plus missing-field fixtures proving tolerant defaults.

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_adapters -v`
Expected: FAIL because adapter modules do not exist.

- [ ] **Step 3: Implement adapters minimally**

Use tolerant `dict.get()` extraction; missing fields become `""`, `None`, `1`, or empty lists as appropriate. Derive `repo` / `commit` from payload when available, store the queue file in `raw_payload_pointer`, and keep `referenced_artifacts` so provenance can cite source artifacts. Do not put frontmatter-only names (`source_agent`, `source_session`, `source_repo`, `source_commit`, `source_artifact`) inside `NormalizedSession`; those are rendered from `tool`, `session_id`, `repo`, `commit`, and classifier bucket.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_adapters -v`
Expected: PASS.

- [ ] **Step 5: Write failing frontmatter renderer tests**

Assert stable key order and valid frontmatter produced from `NormalizedSession`:
`memory_layer`, `project`, `source_agent` (from `tool`, e.g. `copilot-cli`), `source_session` (from `session_id`), `source_artifact` (from classifier bucket, default `session`), `captured_at`, `provenance.repo` (from `repo`), `provenance.commit` (from `commit`), `provenance.path` (from `raw_payload_pointer`), plus body sections for cwd, touched files, referenced artifacts, and prompts.

- [ ] **Step 6: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_frontmatter -v`
Expected: FAIL because renderer does not exist.

- [ ] **Step 7: Implement renderer**

Render YAML-like frontmatter manually with stable ordering and a concise Markdown body containing source, cwd, touched files, and prompts.

- [ ] **Step 8: Run GREEN and commit**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_adapters paulshaclaw.memory.tests.test_frontmatter -v`
Expected: PASS.

Commit:
```bash
git add paulshaclaw/memory/importer paulshaclaw/memory/tests/fixtures paulshaclaw/memory/tests/test_adapters.py paulshaclaw/memory/tests/test_frontmatter.py
git commit -m "feat(stage2): normalize cli session payloads"
```

### Task 3: Idempotent ingestion pipeline and CLI

**Files:**
- Create: `paulshaclaw/memory/tests/test_idempotency.py`
- Create: `paulshaclaw/memory/tests/test_importer_cli.py`
- Create: `paulshaclaw/memory/importer/pipeline.py`
- Create: `paulshaclaw/memory/importer/cli.py`
- Modify: `paulshaclaw/memory/importer/adapters/base.py`

- [ ] **Step 1: Write failing idempotency tests**

Cover first write `written`, same content `hash-duplicate`, higher completeness `updated`, lower completeness `stale-skip`, and `watcher_final` updating `session_end`.

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_idempotency -v`
Expected: FAIL because pipeline does not exist.

- [ ] **Step 3: Implement hash, completeness, ledger, lock, inbox/archive writes**

Hash formula uses spec names:
`sha256(canonical_json((session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))))`.
Completeness tuple:
`(scope_rank, turn_count, len(touched_files), len(user_prompts))` with `{turn:0, subagent:0, session_end:1, watcher_final:2}`.
Append `runtime/ledger/import.jsonl`; archive successful queue payloads under `archive/queue/YYYY-MM/<key>.json`.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_idempotency -v`
Expected: PASS.

- [ ] **Step 5: Write failing CLI tests**

Test `ingest --queue-item payload.json --memory-root <tmp>` writes no files with `--dry-run`, writes inbox and archive without dry-run, and returns non-zero for missing queue item.

- [ ] **Step 6: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_importer_cli -v`
Expected: FAIL because CLI does not exist.

- [ ] **Step 7: Implement CLI**

Expose `python3 -m paulshaclaw.memory.importer.cli ingest --queue-item <path> --memory-root <path> [--dry-run]`.

- [ ] **Step 8: Run GREEN and commit**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_idempotency paulshaclaw.memory.tests.test_importer_cli -v`
Expected: PASS.

Commit:
```bash
git add paulshaclaw/memory/importer paulshaclaw/memory/tests/test_idempotency.py paulshaclaw/memory/tests/test_importer_cli.py
git commit -m "feat(stage2): add idempotent memory importer"
```

---

## Chunk 2: Project resolver, classifier, hooks, docs, OpenSpec closure

### Task 4: Project resolver and classifier routing

**Files:**
- Create: `paulshaclaw/memory/tests/test_project_resolver.py`
- Create: `paulshaclaw/memory/tests/test_classifier.py`
- Create: `paulshaclaw/memory/importer/project_resolver.py`
- Modify: `paulshaclaw/memory/importer/config.py`
- Modify: `paulshaclaw/memory/importer/classifier.py`
- Modify: `paulshaclaw/memory/importer/pipeline.py`
- Create: `config/agents-projects.sample.yaml`
- Modify: `paulshaclaw/memory/hooks/install.sh`

- [ ] **Step 1: Write failing project resolver tests**

Cover cwd longest-prefix, nested monorepo child wins, git toplevel fallback via explicit `git_toplevel`, remote URL match, `_unknown` fallback, and alias collision warning.

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_project_resolver -v`
Expected: FAIL because resolver does not exist.

- [ ] **Step 3: Implement resolver and sample config**

Implement a tiny YAML subset parser for the sample shape: project key with `roots`, `remotes`, `aliases`. Longest path prefix wins; first definition wins on collisions and emits warnings. Add installer behavior so full install writes the template to `<config-root>/agents/config/projects.yaml` when absent, matching the intended `~/.agents/config/projects.yaml` location without writing outside the test root.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_project_resolver -v`
Expected: PASS.

- [ ] **Step 5: Write failing classifier tests**

Use 12 labeled cases: 3 sessions, 3 plans, 3 research, 3 reports. Inputs include filename, touched files, and prompts.

- [ ] **Step 6: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_classifier -v`
Expected: FAIL or fail labels because classifier does not exist.

- [ ] **Step 7: Implement classifier and wire pipeline path**

Rules: explicit plan/task/todo artifacts -> `plans`; research/spec/design docs -> `research`; review/report/test/evidence -> `reports`; default -> `sessions`. Pipeline writes `inbox/<bucket>/<tool>/<YYYY-MM-DD>/<sid>.md`.

- [ ] **Step 8: Run GREEN and commit**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_project_resolver paulshaclaw.memory.tests.test_classifier paulshaclaw.memory.tests.test_idempotency -v`
Expected: PASS.

Commit:
```bash
git add config/agents-projects.sample.yaml paulshaclaw/memory/importer paulshaclaw/memory/tests/test_project_resolver.py paulshaclaw/memory/tests/test_classifier.py
git commit -m "feat(stage2): resolve memory projects and classify inbox"
```

### Task 5: Hook scripts and installer integration

**Files:**
- Create: `paulshaclaw/memory/tests/test_hooks.py`
- Create: `paulshaclaw/memory/hooks/claude_session_end.py`
- Create: `paulshaclaw/memory/hooks/codex_session_end.py`
- Create: `paulshaclaw/memory/hooks/copilot_session_end.py`
- Modify: `paulshaclaw/memory/hooks/install.sh`
- Create: `paulshaclaw/memory/hooks/uninstall.sh`

- [ ] **Step 1: Write failing hook tests**

For each hook, run script with fixture stdin and `PSC_MEMORY_ROOT=<tmp>/memory`; assert `runtime/queue/<tool>__<sid>.json` exists and contains normalized `capture_scope`.

- [ ] **Step 2: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_hooks -v`
Expected: FAIL because scripts do not exist.

- [ ] **Step 3: Implement hook queue writers**

Each script reads stdin JSON, maps tool/capture scope, writes queue payload atomically to `runtime/queue`, and invokes importer best-effort. If importer fails, hook exits zero after queue write and logs a WARN to `log/hooks.log`.

- [ ] **Step 4: Run GREEN**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_hooks -v`
Expected: PASS.

- [ ] **Step 5: Extend installer/uninstaller tests in the same file**

Test full install with `--memory-root`, `--config-root`, and `--repo-root` writes config templates for Claude, Codex, and Copilot under the test config root and writes `<config-root>/agents/config/projects.yaml` from `config/agents-projects.sample.yaml` when absent. Test uninstall removes managed hook config files but preserves inbox content and `projects.yaml`.

- [ ] **Step 6: Run RED**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_hooks -v`
Expected: FAIL because installer only supports tree-only.

- [ ] **Step 7: Implement full install and uninstall**

Install creates hooks venv if possible, copies hook scripts into memory hooks dir, writes user-level config templates under configurable test roots, and prints Codex `/hooks` trust reminder. Uninstall removes managed hook config files only.

- [ ] **Step 8: Run GREEN and commit**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_hooks -v`
Expected: PASS.

Commit:
```bash
git add paulshaclaw/memory/hooks paulshaclaw/memory/tests/test_hooks.py
git commit -m "feat(stage2): install cli memory hooks"
```

### Task 6: Verification docs and OpenSpec archive readiness

**Files:**
- Modify: `paulshaclaw/memory/tests/stage2_integration_check.sh`
- Modify: `paulshaclaw/memory/routing.md`
- Modify: `openspec/changes/stage2-memory-importer-mvp/tasks.md`
- Modify: `openspec/specs/stage2-memory-governance/spec.md`
- Add/modify: `openspec/changes/stage2-memory-importer-mvp/specs/stage2-memory-governance/spec.md`

- [ ] **Step 1: Write failing integration check extension**

Add checks that the importer dry-run command succeeds on a fixture and that frontmatter lint accepts the generated dry-run output.

- [ ] **Step 2: Run RED**

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: FAIL before importer dry-run support is wired into the script.

- [ ] **Step 3: Update integration check and routing docs**

Document repo-local importer MVP and hook boundary. Amend the OpenSpec delta so the archiveable change requires the repo-local importer, hook queue writers, watcher interface contract, and follow-up tracking, but does not claim the external `obs-auto-moc` watcher PR, historical corpus backfill, or 24h burn-in are complete in this repository.

- [ ] **Step 4: Run GREEN**

Run: `bash paulshaclaw/memory/tests/stage2_integration_check.sh`
Expected: PASS and last line `[stage2] ok`.

- [ ] **Step 5: Run focused and full verification**

Run:
```bash
python3 -m unittest discover -s paulshaclaw/memory/tests -v
python3 -m unittest discover -s tests -v
```
Expected: Stage 2 tests PASS. Full repo may retain the known worktree-sensitive Stage 9 baseline failure; if so, record it as pre-existing with command output.

- [ ] **Step 6: Add explicit live hook smoke checklist**

Append a verification checklist to `openspec/changes/stage2-memory-importer-mvp/tasks.md` with the A0 live smoke commands for Claude, Codex, and Copilot:

```bash
PSC_MEMORY_ROOT=<tmp-memory> python3 paulshaclaw/memory/hooks/claude_session_end.py < paulshaclaw/memory/tests/fixtures/claude/session_end/payload.json
PSC_MEMORY_ROOT=<tmp-memory> python3 paulshaclaw/memory/hooks/codex_session_end.py < paulshaclaw/memory/tests/fixtures/codex/stop/payload.json
PSC_MEMORY_ROOT=<tmp-memory> python3 paulshaclaw/memory/hooks/copilot_session_end.py < paulshaclaw/memory/tests/fixtures/copilot/session_end/payload.json
```

Expected: each command creates a non-empty `runtime/queue/<tool>__<sid>.json` and `log/hooks.log` has no `ERROR`. If real interactive CLI sessions are not run in this environment, leave OpenSpec A0 smoke unchecked and document "fixture smoke passed; live CLI smoke deferred".

- [ ] **Step 7: Mark OpenSpec tasks honestly and remove archive ambiguity**

Mark implemented repo-local tasks complete. Convert external `obs-auto-moc`, historical corpus, true live CLI smoke, and 24h burn-in items from active unchecked task checkboxes into a clearly labeled non-checkbox `Deferred follow-up (outside this repo PR)` section with evidence required before that future work can be archived. This preserves honesty while allowing this repo-local OpenSpec change to archive without unchecked tasks.

- [ ] **Step 8: Commit**

```bash
git add paulshaclaw/memory/routing.md paulshaclaw/memory/tests/stage2_integration_check.sh openspec/changes/stage2-memory-importer-mvp openspec/specs/stage2-memory-governance/spec.md docs/superpowers/plans/2026-05-24-stage2-memory-importer-mvp.md
git commit -m "docs(stage2): record memory importer verification"
```

### Final Review, Archive, Policy, Push, PR

- [ ] **Step 1: Request final code review**

Use `superpowers:code-reviewer` with base `origin/main` and current `HEAD`.

- [ ] **Step 2: Address Critical/Important findings**

Fix via TDD if behavior changes are required; rerun relevant tests.

- [ ] **Step 3: Archive OpenSpec change**

If all repo-local tasks are complete and external work is represented as non-checkbox follow-up, sync delta spec to `openspec/specs/stage2-memory-governance/spec.md`, then move `openspec/changes/stage2-memory-importer-mvp` to `openspec/changes/archive/2026-05-24-stage2-memory-importer-mvp`.

- [ ] **Step 4: Policy check**

Run local available checks:
```bash
python3 -m unittest discover -s paulshaclaw/memory/tests -v
bash paulshaclaw/memory/tests/stage2_integration_check.sh
```
If GitHub Actions policy is required, push branch and observe PR check.

- [ ] **Step 5: Commit archive**

```bash
git add openspec docs paulshaclaw config
git commit -m "chore(openspec): archive stage2 memory importer mvp"
```

- [ ] **Step 6: Push and PR**

```bash
git pull --ff-only origin main
git push -u origin stage2-memory-importer-mvp
gh pr create --title "feat(stage2): add memory importer MVP" --body "<summary and test plan>"
```
