# Persona Manager Phase B — Headless 自主派工 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **TDD：每個 production 改動前先寫 failing test 並看它為正確原因 RED。本地 commit、不 push。**

**Goal:** manager 自主路徑改以 headless executor（copilot/claude/codex）啟動 agent，記 session↔task、由 subprocess exit+JSONL 偵測完成、以三家共有 hook（session_start/stop）relay 進度回 PaulShiaBro。

**Architecture:** 兩路徑分流——互動（bot→既有 pane，`route_to_agent`）不動；自主走 headless subprocess argv（無 tmux、無 send-keys）。新增 `AgentLauncher` pluggable seam（3 executor 真實作）；Phase A 的 `build_dispatch_command` 重構為 executor-agnostic 的 `build_dispatch_prompt`；`JobRegistry` 記 executor/session/pid/log；完成偵測 = exit+JSONL；一支共用 relay hook 註冊三家共有事件。

**Tech Stack:** Python 3.12（stdlib `subprocess`/`shutil`/`pathlib`/`json`、`typing.Protocol`）、bash（relay hook）、`unittest`（pytest 跑）。

**設計依據:** `docs/superpowers/specs/2026-06-22-persona-manager-phase-b-headless-dispatch-design.md`（executor 旗標表見其 §3）。

**前置（動工一次）:**
```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git switch feature/persona-manager-phase-a
git switch -c feature/persona-manager-phase-b   # 疊在 A 上（A 未 merge）
git branch --show-current   # 應為 feature/persona-manager-phase-b
```
測試自 repo 根：`python -m pytest <path> -v`。**不得碰 `core/daemon.py: route_to_agent`（路徑 1）。**

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/coordinator/contract_command.py` | Modify | `build_dispatch_command` → `build_dispatch_prompt`（純文字 prompt） |
| `paulshaclaw/coordinator/launcher.py` | Create | `AgentLauncher` Protocol + copilot/claude/codex 三 headless 真實作 |
| `paulshaclaw/coordinator/registry.py` | Modify | job 增 `executor`/`session_name`/`pid`/`log_path`/`exit_code` + 完成偵測 |
| `paulshaclaw/coordinator/autonomy.py` | Modify | `dispatch_ready` 改用 `build_dispatch_prompt` + 注入的 `AgentLauncher` |
| `scripts/coordinator/psc-relay-hook.sh` | Create | 三家共用 relay hook（讀 env+event → bro-bridge） |
| `scripts/coordinator/hooks/{copilot,claude,codex}.*` | Create | 三家 hook 註冊範本（session_start/stop） |
| `tests/test_coordinator_contract_command.py` | Modify | 改測 `build_dispatch_prompt` |
| `tests/test_coordinator_launcher.py` | Create | AgentLauncher argv/seam 測試 |
| `tests/test_coordinator_registry_headless.py` | Create | registry 欄位 + 完成偵測 |
| `tests/test_coordinator_relay_hook.py` | Create | relay payload/fail-safe |
| `tests/test_persona_phase4_fanout_autonomy.py` | Modify | dispatch_ready → launcher 接線 |

---

## Task 1: 分支

- [ ] 1.1 依「前置」開 `feature/persona-manager-phase-b`，`git branch --show-current` 確認。

---

## Task 2: `build_dispatch_command` → `build_dispatch_prompt`

**Files:** Modify `paulshaclaw/coordinator/contract_command.py`、`tests/test_coordinator_contract_command.py`

- [ ] **Step 1: 改寫測試（RED）** — 取代 `tests/test_coordinator_contract_command.py` 全檔：

```python
from __future__ import annotations

import unittest

from paulshaclaw.coordinator.contract_command import build_dispatch_prompt


class BuildDispatchPromptTests(unittest.TestCase):
    def test_carries_contract_task_and_plan(self) -> None:
        p = build_dispatch_prompt("builder", task="persona-phase-b", plan_path="docs/p.md")
        self.assertIn("[PERSONA CONTRACT", p)
        self.assertIn("role: builder", p)
        self.assertIn("persona-phase-b", p)
        self.assertIn("docs/p.md", p)

    def test_no_shell_or_executor_wrapping(self) -> None:
        # executor-agnostic 純文字：不得含 shell/executor 包裝
        p = build_dispatch_prompt("builder", task="t", plan_path="p.md")
        self.assertNotIn("copilot", p)
        self.assertNotIn("--yolo", p)
        self.assertNotIn("-p ", p)

    def test_unknown_role_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_dispatch_prompt("nobody", task="t", plan_path="p.md")

    def test_pure_no_file_read(self) -> None:
        p = build_dispatch_prompt("builder", task="t", plan_path="/nope/x.md")
        self.assertIn("/nope/x.md", p)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 看 RED** — `python -m pytest tests/test_coordinator_contract_command.py -q` → FAIL（`ImportError: build_dispatch_prompt`）。

- [ ] **Step 3: 重構（GREEN）** — 取代 `contract_command.py` 全檔：

```python
from __future__ import annotations

from typing import Mapping

from paulshaclaw.persona import render
from paulshaclaw.persona.contract import PersonaContract


def build_dispatch_prompt(
    role: str,
    *,
    task: str,
    plan_path: str,
    catalog: Mapping[str, PersonaContract] | None = None,
) -> str:
    """強制點 ①：把 persona 契約 render 成 executor-agnostic 純文字 prompt 前言。

    純字串函式、零 I/O：只嵌 plan_path 參照（agent 於 worktree 內自行讀計畫）。
    未知 role → ValueError（由 render_contract_prompt 冒泡）。
    不含任何 shell/executor 包裝；executor argv 由 AgentLauncher 各自組裝（launcher.py）。
    """
    contract_prompt = render.render_contract_prompt(role, catalog)
    return (
        f"{contract_prompt}\n\n"
        f"[TASK] {task}\n"
        f"[PLAN: {plan_path}]\n"
        "請於本 worktree 內讀取上述 plan 並依 persona 契約邊界執行。"
    )
```

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_contract_command.py -q` → PASS。
- [ ] **Step 5: commit**（`feat(coordinator): build_dispatch_command 重構為 executor-agnostic build_dispatch_prompt`，含 Co-Authored-By）。

---

## Task 3: `AgentLauncher` seam + 三 executor

**Files:** Create `paulshaclaw/coordinator/launcher.py`、`tests/test_coordinator_launcher.py`
**參考:** executor 旗標表 = design spec §3。

設計要點（實作須遵守）：
- `LaunchHandle` = dataclass `{executor, session_name, pid, log_path}`。
- `AgentLauncher(Protocol)`：`launch(self, *, slice_id, prompt, worktree, log_dir) -> LaunchHandle`。
- 三真實作各組 argv（**prompt 為單一 argv 元素**），以 `subprocess.Popen(argv, cwd=worktree, env={**os.environ, "PSC_SLICE_ID": slice_id})` 啟動，回 handle（pid=proc.pid）。argv builder 抽成可單測的純函式 `build_<executor>_argv(*, prompt, slice_id, log_dir) -> list[str]`，**真 Popen 與 argv builder 分離**，測試只測 argv builder（不啟真 subprocess）。

- [ ] **Step 1: argv 測試（RED）** — Create `tests/test_coordinator_launcher.py`：

```python
from __future__ import annotations

import unittest

from paulshaclaw.coordinator.launcher import (
    build_copilot_argv,
    build_claude_argv,
    build_codex_argv,
)


class ArgvTests(unittest.TestCase):
    def test_copilot_argv(self) -> None:
        argv = build_copilot_argv(prompt="PROMPT", slice_id="slice-a", log_dir="/lg")
        self.assertEqual(argv[0], "copilot")
        self.assertIn("-p", argv)
        self.assertIn("PROMPT", argv)                 # prompt 為單一元素
        self.assertIn("--remote", argv)
        self.assertIn("--name", argv)
        self.assertIn("slice-a", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("json", argv)

    def test_claude_argv(self) -> None:
        argv = build_claude_argv(prompt="PROMPT", slice_id="slice-a", log_dir="/lg")
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("PROMPT", argv)
        self.assertIn("--output-format", argv)
        self.assertIn("stream-json", argv)

    def test_codex_argv(self) -> None:
        argv = build_codex_argv(prompt="PROMPT", slice_id="slice-a", log_dir="/lg")
        self.assertEqual(argv[0], "codex")
        self.assertIn("exec", argv)
        self.assertIn("PROMPT", argv)
        self.assertIn("--json", argv)

    def test_prompt_is_single_element(self) -> None:
        # prompt 含換行也是單一 argv 元素（headless 的核心保證）
        argv = build_copilot_argv(prompt="line1\nline2", slice_id="s", log_dir="/lg")
        self.assertIn("line1\nline2", argv)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 看 RED** — FAIL（`ModuleNotFoundError: ...launcher`）。

- [ ] **Step 3: 實作（GREEN）** — Create `paulshaclaw/coordinator/launcher.py`。argv builder 依 design spec §3 旗標表組裝；以下為起始實作，**autonomous/remote 細節旗標於 Task 7 smoke test 核定後微調**：

```python
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LaunchHandle:
    executor: str
    session_name: str
    pid: int
    log_path: str


def build_copilot_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return ["copilot", "-p", prompt, "--remote", "--name", slice_id,
            "--log-dir", log_dir, "--output-format", "json", "--allow-all"]


def build_claude_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return ["claude", "-p", prompt, "--output-format", "stream-json",
            "--name", slice_id, "--permission-mode", "acceptEdits"]


def build_codex_argv(*, prompt: str, slice_id: str, log_dir: str) -> list[str]:
    return ["codex", "exec", prompt, "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "-o", str(Path(log_dir) / "last.json")]


@runtime_checkable
class AgentLauncher(Protocol):
    def launch(self, *, slice_id: str, prompt: str, worktree: str, log_dir: str) -> LaunchHandle: ...


_ARGV_BUILDERS = {
    "copilot": build_copilot_argv,
    "claude": build_claude_argv,
    "codex": build_codex_argv,
}


class SubprocessLauncher:
    """真實作：headless subprocess 啟動。測試 MUST 注入 fake，不實體化。"""

    def __init__(self, executor: str = "copilot") -> None:
        if executor not in _ARGV_BUILDERS:
            raise ValueError(f"unknown executor: {executor}")
        self._executor = executor

    def launch(self, *, slice_id: str, prompt: str, worktree: str, log_dir: str) -> LaunchHandle:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        argv = _ARGV_BUILDERS[self._executor](prompt=prompt, slice_id=slice_id, log_dir=log_dir)
        env = {**os.environ, "PSC_SLICE_ID": slice_id}
        log_path = str(Path(log_dir) / f"{slice_id}.jsonl")
        with open(log_path, "ab") as logf:
            proc = subprocess.Popen(argv, cwd=worktree, env=env, stdout=logf, stderr=subprocess.STDOUT)
        return LaunchHandle(executor=self._executor, session_name=slice_id, pid=proc.pid, log_path=log_path)
```

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_launcher.py -q` → PASS（4 passed）。
- [ ] **Step 5: commit**（`feat(coordinator): AgentLauncher seam + copilot/claude/codex headless argv`）。

---

## Task 4: registry 擴充 + 完成偵測

**Files:** Modify `paulshaclaw/coordinator/registry.py`、Create `tests/test_coordinator_registry_headless.py`
**先讀:** `paulshaclaw/coordinator/registry.py` 既有 `create_job`/`get_job`/`list_jobs` 介面，沿用其儲存機制，**新增欄位不破壞既有 Phase 2 測試**。

- [ ] **Step 1: 測試（RED）** — Create `tests/test_coordinator_registry_headless.py`：

```python
from __future__ import annotations

import unittest

from paulshaclaw.coordinator.completion import classify_completion


class CompletionTests(unittest.TestCase):
    def test_exit0_with_success_jsonl_is_done(self) -> None:
        self.assertEqual(
            classify_completion(exit_code=0, last_jsonl_line='{"type":"result","ok":true}'),
            "done",
        )

    def test_nonzero_exit_is_failed(self) -> None:
        self.assertEqual(classify_completion(exit_code=1, last_jsonl_line=None), "failed")

    def test_unparseable_jsonl_fallbacks_to_exit_code(self) -> None:
        self.assertEqual(classify_completion(exit_code=0, last_jsonl_line="not json"), "done")
        self.assertEqual(classify_completion(exit_code=2, last_jsonl_line="not json"), "failed")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 看 RED** — FAIL（`ModuleNotFoundError: ...completion`）。

- [ ] **Step 3: 實作（GREEN）** — Create `paulshaclaw/coordinator/completion.py`：

```python
from __future__ import annotations

import json


def classify_completion(*, exit_code: int, last_jsonl_line: str | None) -> str:
    """exit code + 末筆 JSONL → 'done'/'failed'。JSONL 不可解則 fallback exit code。"""
    if last_jsonl_line:
        try:
            obj = json.loads(last_jsonl_line)
            if isinstance(obj, dict) and obj.get("ok") is False:
                return "failed"
        except (json.JSONDecodeError, TypeError):
            pass  # fallback 到 exit code
    return "done" if exit_code == 0 else "failed"
```

  並在 `registry.py` 的 `create_job` 增可選參數 `executor=None, session_name=None, pid=None, log_path=None, exit_code=None`，寫入 job dict（既有呼叫不傳→None，不破壞 Phase 2 測試）。

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_registry_headless.py -q` → PASS；並跑既有 `tests/test_persona_phase2_coordinator_cli.py` 確認不回歸。
- [ ] **Step 5: commit**（`feat(coordinator): registry 記 headless session 欄位 + completion 偵測`）。

---

## Task 5: 進度 relay hook（三家共有 session_start/stop）

**Files:** Create `scripts/coordinator/psc-relay-hook.sh` + `scripts/coordinator/hooks/{copilot.json,claude.json,codex.json}`、`tests/test_coordinator_relay_hook.py`

- [ ] **Step 1: 測試（RED）** — Create `tests/test_coordinator_relay_hook.py`（以 subprocess 跑 hook script，驗 payload 與 fail-safe）：

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = "scripts/coordinator/psc-relay-hook.sh"


class RelayHookTests(unittest.TestCase):
    def test_emits_slice_tagged_payload(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "relay.out"
            env = {**os.environ, "PSC_SLICE_ID": "slice-a",
                   "PSC_RELAY_TARGET": str(out), "PSC_RELAY_EVENT": "stop"}
            subprocess.run(["bash", HOOK], env=env, check=True)
            text = out.read_text(encoding="utf-8")
            self.assertIn("slice-a", text)
            self.assertIn("stop", text)

    def test_missing_target_does_not_fail(self) -> None:
        # relay 失敗（無 target）MUST NOT 非零退出（fire-and-forget）
        env = {**os.environ, "PSC_SLICE_ID": "slice-a", "PSC_RELAY_EVENT": "stop"}
        env.pop("PSC_RELAY_TARGET", None)
        r = subprocess.run(["bash", HOOK], env=env)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 看 RED** — FAIL（hook 檔不存在）。

- [ ] **Step 3: 實作（GREEN）** — Create `scripts/coordinator/psc-relay-hook.sh`：

```bash
#!/usr/bin/env bash
# 三家共用 relay hook（綁 session_start/stop）。讀 env 標記 slice → 寫 relay channel。
# fire-and-forget：任何失敗都不得非零退出（不連累 agent 執行/完成偵測）。
set -u
slice="${PSC_SLICE_ID:-unknown}"
event="${PSC_RELAY_EVENT:-unknown}"
target="${PSC_RELAY_TARGET:-}"
msg="[manager] slice=${slice} event=${event}"
if [[ -n "$target" ]]; then
  printf '%s\n' "$msg" >>"$target" 2>/dev/null || true
fi
# TODO(GREEN 完成後接 bro-bridge)：若有 bro-bridge CLI，於此 best-effort 推送：
#   command -v tmux-bridge >/dev/null 2>&1 && tmux-bridge send "$msg" 2>/dev/null || true
exit 0
```
  並建三家 hook 註冊範本（事件鎖共有的 session_start/stop，命令呼叫上述 script，PSC_RELAY_EVENT 由各家事件名映射）：`hooks/copilot.json`（`sessionStart`/`agentStop`，`{"version":1,"hooks":{...}}`）、`hooks/claude.json`（settings.json `SessionStart`/`Stop` 片段）、`hooks/codex.json`（`session_start`/`stop`）。`chmod +x psc-relay-hook.sh`。

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_coordinator_relay_hook.py -q` → PASS。
- [ ] **Step 5: commit**（`feat(coordinator): 三家共用進度 relay hook（session_start/stop）`）。

---

## Task 6: `dispatch_ready` 接 headless launcher

**Files:** Modify `paulshaclaw/coordinator/autonomy.py`、`tests/test_persona_phase4_fanout_autonomy.py`
**先讀:** `dispatch_ready` 簽章與 `FanoutTests`/`_FakeDispatcher` 既有結構。

- [ ] **Step 1: 測試（RED）** — 在 `FanoutTests` 加：

```python
    def test_dispatch_ready_launches_via_agent_launcher(self) -> None:
        from paulshaclaw.coordinator.autonomy import dispatch_ready

        calls = []

        class _FakeLauncher:
            def launch(self, *, slice_id, prompt, worktree, log_dir):
                calls.append({"slice_id": slice_id, "prompt": prompt, "worktree": worktree})
                from paulshaclaw.coordinator.launcher import LaunchHandle
                return LaunchHandle(executor="copilot", session_name=slice_id, pid=123, log_path=f"{log_dir}/x")

        metas = [_meta("slice-a", plan="docs/p.md")]
        dispatch_ready(
            metas, is_satisfied=lambda _id: True, dispatcher=_FakeDispatcher(),
            persona="builder", launcher=_FakeLauncher(),
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["slice_id"], "slice-a")
        self.assertIn("[PERSONA CONTRACT", calls[0]["prompt"])
        self.assertIn("docs/p.md", calls[0]["prompt"])
```

- [ ] **Step 2: 看 RED** — FAIL（`dispatch_ready` 無 `launcher` 參數 / 未呼叫）。

- [ ] **Step 3: 實作（GREEN）** — `autonomy.py`：import 改 `from .contract_command import build_dispatch_prompt`；`dispatch_ready` 增 `launcher: AgentLauncher | None = None` 參數；就緒單位若提供 launcher 則 `launcher.launch(slice_id=slice_id, prompt=build_dispatch_prompt(persona, task=slice_id, plan_path=m["plan"]), worktree=<由 dispatcher/worktree 來源>, log_dir=<runtime/dispatch/<slice_id>>)`。保留與既有 Dispatcher 路徑相容（launcher=None 時維持舊行為以不破壞既有測試），或於本 task 一併把舊 pane 路徑切走——**以既有 phase4 測試全綠為準**。

- [ ] **Step 4: GREEN + 不回歸** — `python -m pytest tests/test_persona_phase4_fanout_autonomy.py -q` → PASS。
- [ ] **Step 5: commit**（`feat(coordinator): dispatch_ready 經 AgentLauncher headless 啟動`）。

---

## Task 7: smoke test 待驗（手動，不擋單元測試）

- [ ] 7.1 各跑一次真 executor（在拋棄式 worktree、無害 prompt），確認：hook 是否在 headless fire、autonomous/remote 旗標正確、session id 取得方式。結果回填 design spec §6/§10。
- [ ] 7.2 不 fire hook 的 executor：改由 manager tail JSONL 代為 relay（記入 spec）。

## Task 8: 驗收閘門

- [ ] 8.1 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠（與 CI 同綠；2 例 stage11 cockpit 為既有 textual 偏差，不計）。
- [ ] 8.2 確認 `core/daemon.py: route_to_agent`（路徑 1）未被改動：`git diff main...HEAD -- paulshaclaw/core/daemon.py` 應為空。

---

## Self-Review 紀錄

- **Spec 覆蓋**：`coordinator-headless-dispatch`（AgentLauncher ✓T3、registry+completion ✓T4、relay ✓T5）+ `coordinator-cli`（build_dispatch_prompt ✓T2、dispatch_ready headless ✓T6）。smoke test（spec §6/§10 待驗）✓T7。
- **Placeholder 掃描**：測試與小型確定性碼（build_dispatch_prompt、completion、relay script、argv builder）為完整碼；executor autonomous/remote 細節旗標明列為 T7 smoke-test 待核（已知未知，非 vague placeholder）。T6 worktree 來源依既有 dispatcher 機制，實作時對齊。
- **型別一致**：`build_dispatch_prompt(role,*,task,plan_path,catalog)`、`AgentLauncher.launch(*,slice_id,prompt,worktree,log_dir)->LaunchHandle`、`classify_completion(*,exit_code,last_jsonl_line)`、`build_<exec>_argv(*,prompt,slice_id,log_dir)->list[str]` 全篇一致。
- **不動路徑 1**：T8.2 明列 daemon.py diff 為空閘門。
