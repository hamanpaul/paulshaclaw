# Persona Manager Phase D — canary（#123）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`). **TDD：Unit 1 為 hermetic（注入 fake / stub Popen，不啟真 agent）；Unit 3 為 live 蒐證（由協調者執行）。本地 commit、不 push。**

**Goal:** 加 `--allow-unsafe`/`--model` enabling flags，並用 trivial 有界 canary slice 依序 claude→codex→copilot(haiku-4.5) live 跑一輪，蒐證 dispatch→headless→完成→manifest 全鏈。

**Architecture:** Unit 1 改 `launcher.py`（argv builders + SubprocessLauncher 加 `model`）與 `cli.py`（`tick`/`fanout` 加 `--allow-unsafe`/`--model`，經 `_resolve_launcher` helper 接線）。Unit 2 committed canary fixtures（per-executor 目錄，避免 worktree/job 撞號）。Unit 3 協調者 live 跑並蒐證。

**Tech Stack:** Python 3.12、`unittest`（pytest）、headless CLIs（claude/codex/copilot）。

**設計依據:** `docs/superpowers/specs/2026-06-23-persona-manager-phase-d-canary-design.md`。

**前置:** 分支 `feature/123-phase-d-canary` 已開（off main）。**安全：canary 任務必須 trivial 有界（建一小檔即停）；agent 跑 `feature/<slice>` worktree 隔離。**

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/coordinator/launcher.py` | Modify | 三 argv builder + `SubprocessLauncher` 加 `model` |
| `paulshaclaw/coordinator/cli.py` | Modify | `tick`/`fanout` 加 `--allow-unsafe`/`--model` + `_resolve_launcher` |
| `tests/test_coordinator_launcher.py` | Modify | model passthrough（argv + launch via Popen stub） |
| `tests/test_coordinator_cli_flags.py` | Create | `_resolve_launcher` flag→launcher 接線 |
| `docs/canary/canary.plan.md` | Create | 有界 canary 任務指示 |
| `docs/canary/{claude,codex,copilot}/canary-<e>.md` | Create | 3 個 dispatch:auto slice spec |
| `docs/canary/RUNBOOK.md` | Create | live 跑程序 |

---

## Task 1: argv builder `model` passthrough

**Files:** Modify `paulshaclaw/coordinator/launcher.py`、`tests/test_coordinator_launcher.py`

- [ ] **Step 1: failing tests** — append 到 `tests/test_coordinator_launcher.py` 的 `ArgvTests`：

```python
    def test_copilot_argv_model(self) -> None:
        argv = build_copilot_argv(prompt="P", slice_id="s", log_dir="/lg", model="haiku-4.5")
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "haiku-4.5")

    def test_argv_no_model_when_unset(self) -> None:
        for build in (build_copilot_argv, build_claude_argv, build_codex_argv):
            argv = build(prompt="P", slice_id="s", log_dir="/lg")
            self.assertNotIn("--model", argv, msg=build.__name__)

    def test_claude_codex_argv_model(self) -> None:
        ca = build_claude_argv(prompt="P", slice_id="s", log_dir="/lg", model="opus")
        self.assertIn("--model", ca)
        self.assertEqual(ca[ca.index("--model") + 1], "opus")
        xa = build_codex_argv(prompt="P", slice_id="s", log_dir="/lg", model="gpt-5.4")
        self.assertIn("--model", xa)
        self.assertEqual(xa[xa.index("--model") + 1], "gpt-5.4")
```

- [ ] **Step 2: RED** — `python -m pytest tests/test_coordinator_launcher.py::ArgvTests -v` → FAIL（`build_* got unexpected keyword 'model'`）

- [ ] **Step 3: 實作** — 每個 builder 簽名加 `model: str | None = None`；在 `return argv` 前插入：
```python
    if model is not None:
        argv += ["--model", model]
```
（copilot 在 `if allow_unsafe` 之前插；claude 在 `if worktree is not None` 之前插；codex 在 `argv.extend(["-o", ...])` 之前插。）

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_launcher.py -v` → PASS

- [ ] **Step 5: commit**
```bash
git add paulshaclaw/coordinator/launcher.py tests/test_coordinator_launcher.py
git commit -m "feat(coordinator): #123 argv builder --model passthrough

Refs #123

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `SubprocessLauncher(model=)` → launch 傳遞

**Files:** Modify `paulshaclaw/coordinator/launcher.py`、`tests/test_coordinator_launcher.py`

- [ ] **Step 1: failing test** — append（沿用既有 Popen stub 慣例：覆寫 `launcher_module.subprocess.Popen` 捕捉 argv）：

```python
    def test_subprocess_launcher_passes_model_to_argv(self) -> None:
        captured = {}

        class _FakeProc:
            pid = 4321

        def _fake_popen(argv, **kwargs):
            captured["argv"] = argv
            return _FakeProc()

        original = launcher_module.subprocess.Popen
        launcher_module.subprocess.Popen = _fake_popen
        try:
            with tempfile.TemporaryDirectory() as d:
                SubprocessLauncher("copilot", model="haiku-4.5").launch(
                    slice_id="s", prompt="P", worktree=d, log_dir=d
                )
        finally:
            launcher_module.subprocess.Popen = original
        script = captured["argv"][2]  # ["bash","-lc",script]
        self.assertIn("--model haiku-4.5", script)
```

- [ ] **Step 2: RED** — FAIL（`SubprocessLauncher got unexpected keyword 'model'`）

- [ ] **Step 3: 實作** — `SubprocessLauncher.__init__` 加參數 `model: str | None = None`，存 `self._model = model`；`launch` 內 `_ARGV_BUILDERS[...](...)` 呼叫加一行 `model=self._model,`。

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_launcher.py -v` → PASS

- [ ] **Step 5: commit**
```bash
git add paulshaclaw/coordinator/launcher.py tests/test_coordinator_launcher.py
git commit -m "feat(coordinator): #123 SubprocessLauncher model 傳入 argv builder

Refs #123

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: CLI `--allow-unsafe`/`--model` + `_resolve_launcher`

**Files:** Modify `paulshaclaw/coordinator/cli.py`、Create `tests/test_coordinator_cli_flags.py`

- [ ] **Step 1: failing test** — 建 `tests/test_coordinator_cli_flags.py`：

```python
from __future__ import annotations

import unittest

from paulshaclaw.coordinator.cli import _resolve_launcher
from paulshaclaw.coordinator.launcher import SubprocessLauncher


class ResolveLauncherTests(unittest.TestCase):
    def test_builds_subprocess_launcher_with_flags(self) -> None:
        lr = _resolve_launcher("copilot", None, allow_unsafe=True, model="haiku-4.5")
        self.assertIsInstance(lr, SubprocessLauncher)
        self.assertTrue(lr._allow_unsafe)
        self.assertEqual(lr._model, "haiku-4.5")
        self.assertEqual(lr._executor, "copilot")

    def test_respects_injected_launcher(self) -> None:
        sentinel = object()
        self.assertIs(_resolve_launcher("copilot", sentinel, allow_unsafe=True, model="x"), sentinel)

    def test_none_executor_returns_none(self) -> None:
        self.assertIsNone(_resolve_launcher(None, None, allow_unsafe=False, model=None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: RED** — FAIL（`cannot import name '_resolve_launcher'`）

- [ ] **Step 3: 實作 cli.py**
  在 import 後加 helper：
```python
def _resolve_launcher(executor, injected, *, allow_unsafe, model):
    """注入優先；否則僅在 executor 指定時建 SubprocessLauncher（帶 allow_unsafe/model）。"""
    if injected is not None:
        return injected
    if executor is None:
        return None
    return SubprocessLauncher(executor=executor, allow_unsafe=allow_unsafe, model=model)
```
  `main()` 簽名加 `allow_unsafe` 不需要（讀 args）。在 `_build_parser()` 為 `p_fanout` 與 `p_tick` 各加：
```python
    p_fanout.add_argument("--allow-unsafe", action="store_true")
    p_fanout.add_argument("--model", default=None)
```
（tick 同樣兩行加到 `p_tick`。）
  在 `fanout` handler 把
```python
            active_launcher = launcher
            if active_launcher is None and args.executor is not None:
                active_launcher = SubprocessLauncher(executor=args.executor)
```
  換成
```python
            active_launcher = _resolve_launcher(
                args.executor, launcher, allow_unsafe=args.allow_unsafe, model=args.model
            )
```
  在 `tick` handler 把現有
```python
        active_launcher = launcher
        if active_launcher is None and args.executor is not None:
            active_launcher = SubprocessLauncher(executor=args.executor)
```
  換成同一個 `_resolve_launcher(...)` 呼叫。

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_cli_flags.py tests/test_coordinator_cli_tick.py -v` → PASS

- [ ] **Step 5: commit**
```bash
git add paulshaclaw/coordinator/cli.py tests/test_coordinator_cli_flags.py
git commit -m "feat(coordinator): #123 CLI --allow-unsafe/--model（tick/fanout）

Refs #123

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: canary fixtures + runbook（Unit 2）

**Files:** Create `docs/canary/canary.plan.md`、`docs/canary/{claude,codex,copilot}/canary-<e>.md`、`docs/canary/RUNBOOK.md`

- [ ] **Step 1: 有界 plan** — `docs/canary/canary.plan.md`：
```markdown
# Canary 任務（trivial 有界）

你是 Phase D canary 驗證 agent。**只做這一件事**：在當前 worktree 內建立檔案
`canary/PONG.md`，內容單一行 `pong`。完成後立即停止。

嚴格限制：不要修改/刪除任何其他檔案、不要 git commit/push、不要安裝套件、
不要執行任何與上述無關的指令。這是純粹的「通電」驗證。
```

- [ ] **Step 2: 3 個 slice spec**（每家獨立 slice_id → 獨立 worktree，避免撞號）。
`docs/canary/claude/canary-claude.md`：
```markdown
---
dispatch: auto
slice_id: canary-claude
plan: docs/canary/canary.plan.md
depends_on: []
---
# canary-claude
Phase D canary（claude）。任務見 plan。
```
`docs/canary/codex/canary-codex.md`、`docs/canary/copilot/canary-copilot.md` 同構（slice_id 改 `canary-codex`/`canary-copilot`、標題對應）。

- [ ] **Step 3: RUNBOOK** — `docs/canary/RUNBOOK.md` 記錄 §6 程序、觀測點（manifest/JSONL/sentinel）、清理（移除 `feature/canary-*` worktree）。

- [ ] **Step 4: commit**
```bash
git add docs/canary
git commit -m "test(coordinator): #123 canary fixtures + runbook（有界 dispatch:auto）

Refs #123

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: live run（Unit 3，協調者執行蒐證）

> 依序執行；每家蒐證後再下一家。**非並行。**

- [ ] **Step 1: claude** — `python -m paulshaclaw.coordinator tick --specs-dir docs/canary/claude --executor claude --allow-unsafe`，觀察 worktree 建立 / pid / log；輪詢 `tick`（或 `coordinator complete --handoff-dir runtime/handoff`）直到 `runtime/handoff/canary-claude.json` 出現；貼 manifest + 末筆 JSONL + exit。
- [ ] **Step 2: codex** — `--specs-dir docs/canary/codex --executor codex --allow-unsafe`，同上蒐證。
- [ ] **Step 3: copilot** — `--specs-dir docs/canary/copilot --executor copilot --allow-unsafe --model haiku-4.5`，同上蒐證。
- [ ] **Step 4: record** — 三家結果（pass/fail+原因、耗時、manifest）整理進 PR body / `docs/canary/RESULTS.md`。
- [ ] **Step 5: 清理** — 移除 `feature/canary-*` worktree 與 `runtime/canary` 暫存（保留 record）；確認主工作樹/主分支未被動。

---

## Task 6: 驗證與收尾

- [ ] **Step 1**: `python -m pytest tests/test_coordinator_launcher.py tests/test_coordinator_cli_flags.py tests/test_coordinator_cli_tick.py -q` → PASS
- [ ] **Step 2**: 全 suite 無回歸
- [ ] **Step 3**: code review + `/codex:adversarial-review`（針對 Unit 1 程式碼）
- [ ] **Step 4**: openspec archive + PR（canary record 入 PR body）

---

## Self-Review

- **Spec coverage：** coordinator-headless-dispatch（argv model + launcher model）→Task 1-2；coordinator-cli（--allow-unsafe/--model）→Task 3；canary 驗收→Task 4-5。
- **Placeholder scan：** 無 TBD；code step 附完整程式碼。
- **Type consistency：** `model: str | None=None` 貫穿 builders/launcher；`_resolve_launcher(executor, injected, *, allow_unsafe, model)` 與 cli handler 呼叫一致；`._allow_unsafe`/`._model`/`._executor` 與 SubprocessLauncher 既有屬性一致；canary slice frontmatter（dispatch/slice_id/plan/depends_on）與 `scan_specs`/`ready_units` 期望一致。
