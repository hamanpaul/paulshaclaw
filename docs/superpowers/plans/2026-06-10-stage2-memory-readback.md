# Stage 2 Memory Read-Back Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Stage 2 memory read-back work and be useful — agents (claude/copilot/codex) get a non-empty, correct-project wake-up brief injected, and atoms stop landing in `_unknown`.

**Architecture:** Three surgical changes on top of the working capture pipeline: (A) a guarded `sys.path` bootstrap so deployed hooks resolve the installed `paulshaclaw` package instead of the data-dir namespace shadow; (B) `resolve_project` gains best-effort git auto-detection with a config→repo→folder→tree precedence; (C) a new `codex_session_start.py` wake-up hook wired by `install.sh`.

**Tech Stack:** Python 3.12, stdlib only (`subprocess`, `pathlib`), pytest (`python3 -m pytest`), bash (`install.sh`).

**References:** design `docs/superpowers/specs/2026-06-10-stage2-memory-readback-design.md`; openspec `openspec/changes/stage2-memory-readback/`.

---

## File Structure

- Create `paulshaclaw/memory/importer/_git.py` — bounded best-effort git queries (toplevel, remote, sibling-repo count).
- Modify `paulshaclaw/memory/importer/project_resolver.py` — add the auto-detect precedence chain after the config matches.
- Create `paulshaclaw/memory/hooks/_bootstrap.py` — guarded repo-root `sys.path` insert.
- Modify `paulshaclaw/memory/hooks/{claude,copilot}_session_start.py`, `{claude,copilot}_precompact.py` — use `_bootstrap`.
- Create `paulshaclaw/memory/hooks/codex_session_start.py` — codex wake-up hook.
- Modify `paulshaclaw/memory/hooks/install.sh`, `uninstall.sh` — deploy + wire codex `SessionStart`.
- Tests: `paulshaclaw/memory/tests/test_project_resolver.py`, `test_session_start_hooks.py` (extend); new `test_git_helper.py`.

Test runner (from repo root): `python3 -m pytest paulshaclaw/memory/tests/<file> -q`.

---

## Task 1: Bounded git helper

**Files:**
- Create: `paulshaclaw/memory/importer/_git.py`
- Test: `paulshaclaw/memory/tests/test_git_helper.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_git_helper.py
from __future__ import annotations
import subprocess, unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from paulshaclaw.memory.importer import _git


def _init_repo(path: Path, remote: str | None = None) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)


class GitHelperTests(unittest.TestCase):
    def test_toplevel_and_remote(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "myrepo"
            repo.mkdir()
            _init_repo(repo, "git@github.com:owner/myrepo.git")
            top = _git.git_toplevel(str(repo))
            self.assertEqual(Path(top).resolve(), repo.resolve())
            self.assertEqual(_git.git_remote(top), "git@github.com:owner/myrepo.git")

    def test_non_repo_returns_none(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertIsNone(_git.git_toplevel(tmp))

    def test_sibling_repo_count(self) -> None:
        with TemporaryDirectory() as tmp:
            for name in ("a", "b", "plain"):
                d = Path(tmp) / name
                d.mkdir()
            _init_repo(Path(tmp) / "a")
            _init_repo(Path(tmp) / "b")
            self.assertEqual(_git.sibling_repo_count(str(Path(tmp) / "a")), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_git_helper.py -q`
Expected: FAIL — `ModuleNotFoundError: ... importer._git`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/importer/_git.py
"""Bounded, best-effort git queries for project resolution. Never raises."""
from __future__ import annotations
import subprocess
from pathlib import Path


def _run(args: list[str], cwd: str) -> str | None:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=2, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def git_toplevel(cwd: str | None) -> str | None:
    if not cwd or not Path(cwd).is_dir():
        return None
    return _run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], cwd)


def git_remote(toplevel: str | None) -> str | None:
    if not toplevel:
        return None
    return _run(["git", "-C", toplevel, "remote", "get-url", "origin"], toplevel)


def sibling_repo_count(toplevel: str | None) -> int:
    """Count immediate sibling directories that are git repos (one level only)."""
    if not toplevel:
        return 0
    parent = Path(toplevel).parent
    try:
        children = [p for p in parent.iterdir() if p.is_dir()]
    except OSError:
        return 0
    return sum(1 for p in children if (p / ".git").exists())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_git_helper.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/_git.py paulshaclaw/memory/tests/test_git_helper.py
git commit -m "feat(stage2): bounded best-effort git helper for project resolution"
```

---

## Task 2: Hybrid project resolution precedence

**Files:**
- Modify: `paulshaclaw/memory/importer/project_resolver.py` (`resolve_project`)
- Test: `paulshaclaw/memory/tests/test_project_resolver.py`

- [ ] **Step 1: Write the failing tests** (append to the existing test file)

```python
from tempfile import TemporaryDirectory
import subprocess
from pathlib import Path
from paulshaclaw.memory.importer.project_resolver import resolve_project
from paulshaclaw.memory.importer.config import ProjectsConfig

_EMPTY = ProjectsConfig(projects=())  # no configured projects → exercise auto-detect


def _init(path: Path, remote: str | None = None) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if remote:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote], check=True)


class ResolveAutoDetectTests(unittest.TestCase):
    def test_repo_with_remote_resolves_owner_repo(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "paulshaclaw"; repo.mkdir()
            _init(repo, "git@github.com:hamanpaul/paulshaclaw.git")
            self.assertEqual(resolve_project(cwd=str(repo), projects=_EMPTY), "github.com/hamanpaul/paulshaclaw")

    def test_repo_without_remote_resolves_dir_name(self) -> None:
        with TemporaryDirectory() as tmp:
            repo = Path(tmp) / "solo"; repo.mkdir()
            _init(repo)
            self.assertEqual(resolve_project(cwd=str(repo), projects=_EMPTY), "solo")

    def test_not_a_repo_resolves_working_folder(self) -> None:
        with TemporaryDirectory() as tmp:
            d = Path(tmp) / "scratchpad"; d.mkdir()
            self.assertEqual(resolve_project(cwd=str(d), projects=_EMPTY), "scratchpad")

    def test_multi_repo_workspace_resolves_tree_path(self) -> None:
        with TemporaryDirectory() as tmp:
            ws = Path(tmp) / "work_prj"; ws.mkdir()
            a = ws / "serialwrap"; a.mkdir(); _init(a)   # no remote → falls to tree
            b = ws / "other"; b.mkdir(); _init(b)
            self.assertEqual(resolve_project(cwd=str(a), projects=_EMPTY), "work_prj/serialwrap")

    def test_truly_unresolvable_is_unknown(self) -> None:
        self.assertEqual(resolve_project(cwd=None, projects=_EMPTY), "_unknown")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_project_resolver.py -q -k AutoDetect`
Expected: FAIL — repo cases return `_unknown` (no auto-detect yet)

- [ ] **Step 3: Implement the precedence chain**

In `project_resolver.py`, add `from pathlib import Path` and `from . import _git` to imports, then replace the final `return "_unknown"` of `resolve_project` with:

```python
    # Auto-detect (best-effort) when config did not match.
    toplevel = git_toplevel or _git.git_toplevel(cwd)
    if toplevel:
        remote = normalize_remote(remote_url or _git.git_remote(toplevel))
        if remote:
            return remote  # owner/repo (config remote-match above already tried config)
        name = Path(toplevel).name
        if _git.sibling_repo_count(toplevel) >= 2:
            return f"{Path(toplevel).parent.name}/{name}"
        return name
    if cwd:
        return Path(cwd).name  # not in a repo → working-folder name
    return "_unknown"
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_project_resolver.py -q`
Expected: PASS (existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/project_resolver.py paulshaclaw/memory/tests/test_project_resolver.py
git commit -m "feat(stage2): hybrid project resolution (config > repo > folder > tree)"
```

---

## Task 3: Populate provenance.repo from the detected remote

**Files:**
- Modify: the importer module that sets atom `provenance` (currently `repo: _unknown`)
- Test: that module's existing test file

- [ ] **Step 1: Locate the provenance assignment**

Run: `grep -rn "provenance" paulshaclaw/memory/importer/ | grep -i repo`
Identify where `provenance.repo` (or the `repo` field) is set to `_unknown`. Read that function and its test.

- [ ] **Step 2: Write a failing test** asserting that, given a cwd inside a repo with remote `git@github.com:owner/x.git`, the built atom's `provenance.repo` equals `github.com/owner/x` (use `normalize_remote(_git.git_remote(_git.git_toplevel(cwd)))`). Mirror the existing provenance test's construction.

- [ ] **Step 3: Implement** — at the provenance assignment, replace the `_unknown` default with the detected, normalized remote (falling back to `_unknown` when none):

```python
from .project_resolver import normalize_remote
from . import _git
_remote = normalize_remote(_git.git_remote(_git.git_toplevel(cwd)))
repo = _remote or "_unknown"
```

- [ ] **Step 4: Run** the provenance test file: `python3 -m pytest paulshaclaw/memory/tests/<that_test>.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/importer/ paulshaclaw/memory/tests/
git commit -m "feat(stage2): fill atom provenance.repo from git remote"
```

---

## Task 4: Guarded hook bootstrap (fixes the read-back shadow)

**Files:**
- Create: `paulshaclaw/memory/hooks/_bootstrap.py`
- Modify: `paulshaclaw/memory/hooks/{claude,copilot}_session_start.py`, `{claude,copilot}_precompact.py`
- Test: `paulshaclaw/memory/tests/test_session_start_hooks.py`

- [ ] **Step 1: Write the failing test** (append)

```python
import importlib.util, sys
HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"

def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("_bootstrap", HOOKS_DIR / "_bootstrap.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod

class BootstrapGuardTests(unittest.TestCase):
    def test_does_not_insert_a_non_package_dir(self):
        bs = _load_bootstrap()
        with tempfile.TemporaryDirectory() as tmp:
            # simulate the data-dir layout: <tmp>/paulshaclaw/ WITHOUT __init__.py,
            # and a hook file 3 levels deep so parents[3] == <tmp>
            hookfile = Path(tmp) / "paulshaclaw" / "memory" / "hooks" / "h.py"
            hookfile.parent.mkdir(parents=True)
            hookfile.write_text("")
            before = list(sys.path)
            bs.ensure_repo_on_path(_hook_file=str(hookfile))
            self.assertEqual(sys.path, before)  # tmp NOT inserted (no paulshaclaw/__init__.py)

    def test_inserts_a_real_package_root(self):
        bs = _load_bootstrap()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "paulshaclaw").mkdir()
            (Path(tmp) / "paulshaclaw" / "__init__.py").write_text("")
            hookfile = Path(tmp) / "paulshaclaw" / "memory" / "hooks" / "h.py"
            hookfile.parent.mkdir(parents=True); hookfile.write_text("")
            try:
                bs.ensure_repo_on_path(_hook_file=str(hookfile))
                self.assertIn(tmp, sys.path)
            finally:
                if tmp in sys.path:
                    sys.path.remove(tmp)
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_session_start_hooks.py -q -k Bootstrap`
Expected: FAIL — `_bootstrap.py` does not exist

- [ ] **Step 3: Create `_bootstrap.py`**

```python
# paulshaclaw/memory/hooks/_bootstrap.py
"""Add the repo root to sys.path ONLY when it is a real package root.

Deployed hooks live under the memory data dir, whose `paulshaclaw/` is a
namespace dir (no __init__.py) that would shadow the installed package. Guard
on `paulshaclaw/__init__.py` so we never insert that shadow; the hooks venv's
installed package resolves imports in the deployed case.
"""
from __future__ import annotations
import sys
from pathlib import Path


def ensure_repo_on_path(_hook_file: str | None = None) -> None:
    hook_file = Path(_hook_file).resolve() if _hook_file else Path(__file__).resolve()
    root = hook_file.parents[3]
    if (root / "paulshaclaw" / "__init__.py").is_file() and str(root) not in sys.path:
        sys.path.insert(0, str(root))
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_session_start_hooks.py -q -k Bootstrap`
Expected: PASS (2 tests)

- [ ] **Step 5: Swap the inline block in the 4 hooks**

In each of `claude_session_start.py`, `copilot_session_start.py`, `claude_precompact.py`, `copilot_precompact.py`, replace:

```python
# Add repo root to sys.path for imports when running from repo
_hook_file = Path(__file__).resolve()
_repo_root = _hook_file.parents[3]
if _repo_root not in sys.path:
    sys.path.insert(0, str(_repo_root))
```

with:

```python
import _bootstrap  # sibling module; hooks dir is on sys.path[0]
_bootstrap.ensure_repo_on_path()
```

- [ ] **Step 6: Run the full hook suite**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_session_start_hooks.py paulshaclaw/memory/tests/test_hooks.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/memory/hooks/_bootstrap.py paulshaclaw/memory/hooks/claude_session_start.py paulshaclaw/memory/hooks/copilot_session_start.py paulshaclaw/memory/hooks/claude_precompact.py paulshaclaw/memory/hooks/copilot_precompact.py paulshaclaw/memory/tests/test_session_start_hooks.py
git commit -m "fix(stage2): guard hook sys.path bootstrap (fixes read-back import shadow)"
```

---

## Task 5: codex wake-up hook

**Files:**
- Create: `paulshaclaw/memory/hooks/codex_session_start.py`
- Test: `paulshaclaw/memory/tests/test_session_start_hooks.py`

- [ ] **Step 1: Confirm the codex SessionStart output contract**

Read `~/.codex/plugins/cache/openai-codex/codex/1.0.4/hooks/hooks.json` and the codex hook docs to confirm the injected-context field. Default assumption (verified shape used by claude/copilot under the same protocol): `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": <brief>}}`. If codex differs, adjust the output dict in Step 3 only.

- [ ] **Step 2: Write the failing test** (append) — run `codex_session_start.py` as a subprocess with a SessionStart payload and assert it prints valid JSON whose injected-context equals the brief from `compute_brief` (patch/stub a known project), and that an error path still prints empty context + exit 0. Mirror the existing claude subprocess test in this file.

- [ ] **Step 3: Create `codex_session_start.py`** (mirror `claude_session_start.py` with the new bootstrap)

```python
#!/usr/bin/env python3
"""Codex SessionStart hook — inject the memory wake-up brief. Fail-safe: exit 0."""
from __future__ import annotations
import json, sys
from pathlib import Path

import _bootstrap  # sibling module; hooks dir is on sys.path[0]
_bootstrap.ensure_repo_on_path()

TOOL = "codex"


def main() -> int:
    from paulshaclaw.memory.hooks._wakeup_common import compute_brief, log_warn, memory_root, read_payload
    root = memory_root()
    payload = read_payload(root, TOOL)
    brief = ""
    try:
        brief = compute_brief(root, payload.get("cwd"))
    except Exception as exc:
        log_warn(root, TOOL, f"failed to build output: {exc}")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": brief}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_session_start_hooks.py -q -k codex`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/codex_session_start.py paulshaclaw/memory/tests/test_session_start_hooks.py
git commit -m "feat(stage2): add codex_session_start wake-up hook"
```

---

## Task 6: install.sh / uninstall.sh codex wiring

**Files:**
- Modify: `paulshaclaw/memory/hooks/install.sh`, `paulshaclaw/memory/hooks/uninstall.sh`
- Test: `paulshaclaw/memory/tests/test_hooks.py` (or the install test, if present)

- [ ] **Step 1: Add the script to the deploy list**

In `install.sh`, add `codex_session_start.py` to the `for script in …` copy list (currently lines ~167-170, alongside `codex_session_end.py`).

- [ ] **Step 2: Read the existing codex reconcile block**

Run: `grep -n "codex\|hooks.json\|_reconcile\|SessionStart\|Stop" paulshaclaw/memory/hooks/install.sh`
Locate where `~/.codex/hooks.json` is reconciled for `Stop`/`SubagentStop` (managedBy `paulsha-memory`).

- [ ] **Step 3: Wire codex SessionStart**

Mirror the existing codex reconcile: add a `SessionStart` entry running `${venv_python} ${hook_dir}/codex_session_start.py` with `managedBy: paulsha-memory` (matcher `startup|clear|compact`), preserving existing `Stop`/`SubagentStop` entries. In `uninstall.sh`, add `codex_session_start.py` to the removed scripts and drop the codex `SessionStart` managed entry.

- [ ] **Step 4: Test the wiring with a temp config root**

Run: `python3 -m pytest paulshaclaw/memory/tests/test_hooks.py -q`
Expected: PASS. If an install test asserts the codex hook set, extend it to expect the `SessionStart` entry. Manually verify against a temp root:
`bash paulshaclaw/memory/hooks/install.sh --skip-venv --memory-root /tmp/m --config-root /tmp/c` then `python3 -m json.tool /tmp/c/.codex/hooks.json | grep -A2 SessionStart`.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/hooks/install.sh paulshaclaw/memory/hooks/uninstall.sh paulshaclaw/memory/tests/test_hooks.py
git commit -m "feat(stage2): install/uninstall wire codex SessionStart wake-up hook"
```

---

## Task 7: Full suite + deploy + acceptance

- [ ] **Step 1: Run the whole memory suite + repo suite**

Run: `python3 -m pytest paulshaclaw/memory/tests -q && .venv/bin/python -m unittest discover -s tests -q`
Expected: all green.

- [ ] **Step 2: Redeploy hooks**

Run: `bash paulshaclaw/memory/hooks/install.sh` (full). Confirm the deployed copies updated:
`grep -n ensure_repo_on_path ~/.agents/memory/hooks/claude_session_start.py` and `ls ~/.agents/memory/hooks/codex_session_start.py ~/.agents/memory/hooks/_bootstrap.py`.

- [ ] **Step 3: Acceptance — read-back injects, no WARN**

Run the deployed claude wake-up hook with a real cwd and assert non-empty + no new WARN:
```bash
n0=$(wc -l < ~/.agents/memory/log/hooks.log)
echo '{"hook_event_name":"SessionStart","cwd":"'"$PWD"'","session_id":"acc"}' | \
  PSC_MEMORY_ROOT=$HOME/.agents/memory ~/.agents/memory/hooks/.venv/bin/python ~/.agents/memory/hooks/claude_session_start.py | python3 -c "import sys,json;print('len',len(json.load(sys.stdin)['hookSpecificOutput']['additionalContext']))"
n1=$(wc -l < ~/.agents/memory/log/hooks.log); echo "new WARN lines: $((n1-n0))"
```
Expected: `len` > 0 for a project with atoms (e.g. paulshaclaw); `new WARN lines: 0`.

- [ ] **Step 4: Acceptance — resolution covers repos**

In a couple of real repos, confirm `resolve_project` no longer returns `_unknown`:
`python3 -c "from paulshaclaw.memory.importer.project_resolver import resolve_project as r; print(r(cwd='$PWD'))"`

- [ ] **Step 5: Update CHANGELOG + openspec status**

Add a `### Fixed` CHANGELOG entry. Run `openspec status --change stage2-memory-readback`.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(stage2): changelog for memory read-back fix"
```

---

## Self-Review

- **Spec coverage:** Wake-up injection (T4 fix + T1-T2 resolution + T7 accept) ✓; install-independent bootstrap (T4) ✓; hybrid resolution incl. tree (T2) ✓; provenance.repo (T3) ✓; codex coverage (T5-T6) ✓; capture unchanged (no capture files touched) ✓; crash-safety (hooks keep catch-all; T5 fail path tested) ✓.
- **Placeholder scan:** Tasks 3 and 6 contain explicit *discovery* steps (grep to locate the provenance assignment / codex reconcile block) rather than guessed line numbers — these are verifiable actions, not vague placeholders; all code-bearing steps show real code.
- **Type consistency:** `_git.git_toplevel/git_remote/sibling_repo_count` and `_bootstrap.ensure_repo_on_path(_hook_file=…)` signatures are used consistently across tasks; `normalize_remote` reused from the existing resolver.
