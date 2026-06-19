# Persona Phase 2 — Minimal Coordinator CLI（job registry + seams + dispatcher + CLI）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付設計 §7 / §11 Phase 2 的 minimal coordinator CLI——manager 的派工原語。一個**自我封裝、可完整單元測試**的新 package `paulshaclaw/coordinator/`，四個模組：`registry.py`（job CRUD + JSON 持久化 + 確定性 job_id + corrupt fail-closed）、`seams.py`（`PaneSender`/`WorktreeCreator` Protocol + 真實作 `TmuxPaneSender`/`ScriptWorktreeCreator`）、`dispatcher.py`（建 worktree→送命令→記 job + `poll_done` 完成偵測）、`cli.py`+`__main__.py`（`dispatch`/`jobs`/`stat`，`main(argv)` 可注入）。

**Architecture:** 鐵律——**所有副作用藏在可注入 seam 後，單元測試一律注入 fake**：不啟動真 copilot、真 tmux、真 git worktree。

- `registry.JobRegistry`：確定性 `job_id = f"{task}-{seq}"`，`seq` 為 **registry-wide 單調計數器**（**非 per-task、非時間、非亂數** → 測試可硬斷言）。故同一 registry 內依序派 task `a` 再 `b` 得 `a-1`、`b-2`（seq 全域遞增，跨 task 唯一）。狀態檔 `{"seq": int, "jobs": [..]}`，corrupt → raise（fail-closed，呼應 `loader.load_catalog`/`handoff.read_manifest`）。
- `seams.PaneSender`/`WorktreeCreator`：`typing.Protocol`；真實作鏡射既有零件（`TmuxPaneSender` ↔ `daemon._send_to_pane`；`ScriptWorktreeCreator` ↔ `using-git-worktrees.sh` 新分支路徑）；真實作**不**進單元測試。
- `dispatcher.Dispatcher`：`dispatch` 建 worktree→送命令→記 job→回 job（worktree 失敗則不送/不記，fail-closed）；`poll_done(job_id, git_runner)` 以 branch 新 commit 標 done（`git_runner` 注入 seam）。
- `cli.main(argv, *, registry=None, pane_sender=None, worktree_creator=None)`：argparse 子命令；未注入接真實作、注入用 fake。

**Tech Stack:** Python 3.12、`unittest`、stdlib（`json`、`subprocess`、`argparse`、`pathlib`、`tempfile`、`typing`）。無新增外部依賴。

**Hard constraints（務必遵守）:**
- **不改** `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`（scope 紀律）；本階段只新建 `paulshaclaw/coordinator/` package，**不**把 `LocalCoordinator` 換成新 registry。
- 測試**不得**啟動真 copilot/真 tmux/真 git worktree——一律注入 fake。
- job_id **必須確定性**（task + 注入計數器），**禁** `time`/`uuid`/`random`。

**Out of scope（後續階段）:** persona contract render／gate（Phase 1 已交付）；`persona-scope.yml` CI（Phase 3）；frontmatter `dispatch:auto` triage（Phase 4）；把 daemon 接到真 coordinator（後續 wiring）；copilot 完成偵測終局選型（§13，本階段先 branch-commit + 可換 seam）。

---

## File Structure

- Commit-only（Task 1）：`openspec/changes/persona-phase2-coordinator-cli/**`、本 plan
- Create: `tests/test_persona_phase2_coordinator_cli.py` — 四組 RED 測試（registry/seams/dispatcher/cli）
- Create: `paulshaclaw/coordinator/__init__.py` — 匯出 `registry`/`seams`/`dispatcher`/`cli`
- Create: `paulshaclaw/coordinator/registry.py` — `JobRegistry`
- Create: `paulshaclaw/coordinator/seams.py` — Protocol + `TmuxPaneSender`/`ScriptWorktreeCreator`
- Create: `paulshaclaw/coordinator/dispatcher.py` — `Dispatcher`
- Create: `paulshaclaw/coordinator/cli.py` — `main(argv, *, ...)`
- Create: `paulshaclaw/coordinator/__main__.py` — `sys.exit(cli.main())`

**全套件測試指令（CI 同款）：** `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
**既知環境失敗（忽略）：** `tests/test_stage11_operator_cockpit.py` 2 筆（`query_one` / textual 未裝於 system python3）。其餘任何失敗皆為真。

---

### Task 1: 提交規劃 artifacts

**Files:**
- Commit: `openspec/changes/persona-phase2-coordinator-cli/`（proposal/design/specs/tasks/.openspec.yaml）、本 plan

- [ ] **Step 1: 確認分支與待提交檔**

Run: `git branch --show-current && git status --short`
Expected: 分支 `feature/persona-phase2-coordinator-cli`；列出未追蹤的 `openspec/changes/persona-phase2-coordinator-cli/` 與本 plan。

- [ ] **Step 2: openspec 驗證**

Run: `openspec validate persona-phase2-coordinator-cli --strict`
Expected: `Change 'persona-phase2-coordinator-cli' is valid`。

- [ ] **Step 3: 提交（本 step 由 controller 在本任務外已執行；若重跑流程才需）**

> 註：本計畫的 openspec change + plan 已於 `docs(coordinator): Phase 2 openspec change + plan` 一次 docs commit 提交。Task 1 在實作 session 中僅需確認 artifacts 在位、validate 通過，**不重複提交**。

---

### Task 2: registry.py（job 持久化 + 確定性 id + fail-closed）— TDD

**Files:**
- Test: `tests/test_persona_phase2_coordinator_cli.py`（新增檔首 import + `JobRegistryTests`）
- Create: `paulshaclaw/coordinator/registry.py`

- [ ] **Step 1: 寫失敗測試（RED）**

建立 `tests/test_persona_phase2_coordinator_cli.py`，放共用 import 與 `JobRegistryTests`：

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class JobRegistryTests(unittest.TestCase):
    def test_create_get_update_deterministic_id(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            job1 = reg.create_job(
                task="mytask", persona="builder",
                branch="feature/mytask", pane="%1", worktree="/wt/mytask",
            )
            # 確定性 job_id：task + 單調計數器，非時間/亂數
            self.assertEqual(job1["job_id"], "mytask-1")
            self.assertEqual(job1["task"], "mytask")
            self.assertEqual(job1["persona"], "builder")
            self.assertEqual(job1["branch"], "feature/mytask")
            self.assertEqual(job1["pane"], "%1")
            self.assertEqual(job1["worktree"], "/wt/mytask")
            self.assertEqual(job1["status"], "dispatched")
            self.assertIn("created_at", job1)

            # 同 task 再建 → 單調遞增，不撞號
            job2 = reg.create_job(
                task="mytask", persona="builder",
                branch="feature/mytask-2", pane="%2", worktree="/wt/mytask-2",
            )
            self.assertEqual(job2["job_id"], "mytask-2")

            self.assertEqual(reg.get_job("mytask-1"), job1)
            self.assertEqual(len(reg.list_jobs()), 2)

            updated = reg.update_status("mytask-1", "done")
            self.assertEqual(updated["status"], "done")
            self.assertEqual(reg.get_job("mytask-1")["status"], "done")

    def test_update_status_rejects_unknown(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            reg.create_job(task="t", persona="builder",
                           branch="b", pane="%1", worktree="/wt/t")
            with self.assertRaises(ValueError):
                reg.update_status("t-1", "bogus")        # 非法 status
            with self.assertRaises(KeyError):
                reg.update_status("nope-9", "done")       # 不存在 job

    def test_persistence_round_trip(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "jobs.json"
            reg = JobRegistry(state_path=state)
            reg.create_job(task="alpha", persona="builder",
                           branch="feature/alpha", pane="%3", worktree="/wt/alpha")
            # 新 registry 指向同一檔 → 讀回
            reg2 = JobRegistry(state_path=state)
            jobs = reg2.list_jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["job_id"], "alpha-1")
            self.assertEqual(reg2.get_job("alpha-1")["worktree"], "/wt/alpha")
            # 重載後新 job 續編、不撞號
            job_b = reg2.create_job(task="alpha", persona="builder",
                                    branch="feature/alpha-b", pane="%4", worktree="/wt/alpha-b")
            self.assertEqual(job_b["job_id"], "alpha-2")

    def test_corrupt_state_fails_closed(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / "jobs.json"
            state.write_text("{ this is not valid json", encoding="utf-8")
            with self.assertRaises(ValueError):
                JobRegistry(state_path=state)   # fail-closed：不可靜默清空

    def test_missing_state_is_empty_registry(self) -> None:
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "absent.json")
            self.assertEqual(reg.list_jobs(), [])   # 不存在非錯誤


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED 為預期原因**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::JobRegistryTests -q`
Expected: RED，原因為 `ModuleNotFoundError: No module named 'paulshaclaw.coordinator'`（缺 package）。捕捉輸出為證據。

- [ ] **Step 3: 建立 package + 實作 registry.py（GREEN）**

先建 `paulshaclaw/coordinator/__init__.py`（Task 6 會補全匯出，此處先放最小可 import；為避免 Task 2 引入尚未存在的 seams/dispatcher，此 step 先寫**空檔**）：

```python
"""Stage4 persona Phase 2 minimal coordinator CLI package."""
```

建立 `paulshaclaw/coordinator/registry.py`：

```python
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

# job.status 合法值（設計 §7 / spec）
VALID_STATUSES = frozenset({"dispatched", "running", "done", "failed"})

DEFAULT_STATE_PATH = Path.home() / ".agents" / "coordinator" / "jobs.json"


def _now_iso() -> str:
    # created_at 用於人讀/排序；job_id 不含時間（確定性由 _seq 保證）
    return datetime.now(timezone.utc).isoformat()


class JobRegistry:
    """Job 狀態的持久化 registry。

    - job_id 確定性：f"{task}-{seq}"，seq 為內部單調計數器（非時間/亂數）。
    - 狀態檔結構：{"seq": int, "jobs": [job, ...]}，JSON 持久化。
    - corrupt/不可解析狀態檔 → raise（fail-closed），MUST NOT 靜默清空。
    - 狀態檔不存在 → 空 registry（首次使用，非錯誤）。
    """

    def __init__(self, state_path: str | Path | None = None, seq_start: int = 0) -> None:
        self._state_path = Path(state_path) if state_path is not None else DEFAULT_STATE_PATH
        self._jobs: list[dict[str, object]] = []
        self._seq = seq_start
        self._load()

    # ---- persistence ----
    def _load(self) -> None:
        if not self._state_path.is_file():
            return  # 不存在 → 空 registry
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"coordinator 狀態檔解析失敗（fail-closed）: {self._state_path}: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError(f"coordinator 狀態檔格式錯誤（fail-closed）: {self._state_path}")
        seq = payload.get("seq", 0)
        if not isinstance(seq, int):
            raise ValueError(f"coordinator 狀態檔 seq 型別錯誤（fail-closed）: {self._state_path}")
        self._jobs = [dict(job) for job in payload["jobs"]]
        # 重載後計數器續編：max(載入 seq, 現有 job 數)，避免撞號
        self._seq = max(seq, self._seq)

    def _persist(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seq": self._seq, "jobs": self._jobs}
        # 原子寫：先寫暫存再 replace，避免中斷留半檔
        fd, tmp = tempfile.mkstemp(dir=str(self._state_path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self._state_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise

    # ---- CRUD ----
    def create_job(
        self,
        *,
        task: str,
        persona: str,
        branch: str,
        pane: str,
        worktree: str,
    ) -> dict[str, object]:
        self._seq += 1
        job: dict[str, object] = {
            "job_id": f"{task}-{self._seq}",
            "task": task,
            "persona": persona,
            "branch": branch,
            "pane": pane,
            "worktree": worktree,
            "status": "dispatched",
            "created_at": _now_iso(),
        }
        self._jobs.append(job)
        self._persist()
        return dict(job)

    def list_jobs(self) -> list[dict[str, object]]:
        return [dict(job) for job in self._jobs]

    def get_job(self, job_id: str) -> dict[str, object]:
        for job in self._jobs:
            if job["job_id"] == job_id:
                return dict(job)
        raise KeyError(f"job 不存在: {job_id}")

    def update_status(self, job_id: str, status: str) -> dict[str, object]:
        if status not in VALID_STATUSES:
            raise ValueError(f"非法 status: {status!r}（須為 {sorted(VALID_STATUSES)} 之一）")
        for job in self._jobs:
            if job["job_id"] == job_id:
                job["status"] = status
                self._persist()
                return dict(job)
        raise KeyError(f"job 不存在: {job_id}")
```

> 注意：`create_job` 用 keyword-only（`*`）以強制呼叫端具名，避免位置參數錯位。測試與 dispatcher 皆以具名呼叫。

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::JobRegistryTests -q`
Expected: 5 passed。

---

### Task 3: seams.py（Protocol + 真實作，真實作不進測試）— TDD

**Files:**
- Test: `tests/test_persona_phase2_coordinator_cli.py`（新增 `SeamProtocolTests`）
- Create: `paulshaclaw/coordinator/seams.py`

- [ ] **Step 1: 寫失敗測試（RED）**

在 `tests/test_persona_phase2_coordinator_cli.py` 的 `JobRegistryTests` 之後、`if __name__` 之前插入。同時把 fake seam 放在此（dispatcher/cli 測試會 reuse）：

```python
# ---- fakes（dispatcher / cli 測試共用；真實作不進任何測試）----
class FakePaneSender:
    """記錄 send 呼叫的 fake；結構相容 seams.PaneSender。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, pane_id: str, text: str) -> None:
        self.sent.append((pane_id, text))


class FakeWorktreeCreator:
    """回固定路徑並記錄 branch 的 fake；結構相容 seams.WorktreeCreator。"""

    def __init__(self, root: str = "/fake/wt") -> None:
        self.root = root
        self.created: list[str] = []

    def create(self, branch: str) -> str:
        self.created.append(branch)
        return f"{self.root}/{branch.replace('/', '-')}"


class SeamProtocolTests(unittest.TestCase):
    def test_fakes_satisfy_protocols(self) -> None:
        from paulshaclaw.coordinator import seams

        sender: seams.PaneSender = FakePaneSender()
        creator: seams.WorktreeCreator = FakeWorktreeCreator()
        sender.send("%9", "hello")
        path = creator.create("feature/x")
        self.assertEqual(path, "/fake/wt/feature-x")
        # 真實作存在且為對應型別（不呼叫其副作用方法）
        self.assertTrue(hasattr(seams, "TmuxPaneSender"))
        self.assertTrue(hasattr(seams, "ScriptWorktreeCreator"))
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::SeamProtocolTests -q`
Expected: RED，`ModuleNotFoundError: No module named 'paulshaclaw.coordinator.seams'`。

- [ ] **Step 3: 實作 seams.py（GREEN）**

建立 `paulshaclaw/coordinator/seams.py`：

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class PaneSender(Protocol):
    """把一行命令送進 tmux pane 的 seam。"""

    def send(self, pane_id: str, text: str) -> None: ...


@runtime_checkable
class WorktreeCreator(Protocol):
    """為某分支建立 git worktree、回傳其路徑的 seam。"""

    def create(self, branch: str) -> str: ...


class TmuxPaneSender:
    """真實作：鏡射 daemon._send_to_pane。

    `tmux send-keys -t <pane> -l <text>`（literal，避免 shell 二次解讀）
    後 `tmux send-keys -t <pane> Enter`。失敗 → raise ValueError。
    單元測試 MUST 注入 fake，不實體化此類。
    """

    def send(self, pane_id: str, text: str) -> None:
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "-l", text],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_id, "Enter"],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"tmux send-keys failed: {exc.stderr.decode().strip()}") from exc
        except FileNotFoundError as exc:
            raise ValueError("tmux not found") from exc


class ScriptWorktreeCreator:
    """真實作：鏡射 scripts/using-git-worktrees.sh 的新分支路徑。

    `git -C <repo> worktree add -b <branch> <wt_root>/<slug> <base>`，
    回傳 target 路徑。單元測試 MUST 注入 fake，不實體化此類。
    """

    def __init__(
        self,
        repo: str | Path = "/home/paul_chen/prj_pri/paulshaclaw",
        wt_root: str | Path = "/home/paul_chen/prj_pri/paulshaclaw-worktrees",
        base: str = "main",
    ) -> None:
        self._repo = Path(repo)
        self._wt_root = Path(wt_root)
        self._base = base

    def create(self, branch: str) -> str:
        slug = branch.replace("/", "-")
        target = self._wt_root / slug
        self._wt_root.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "-C", str(self._repo), "worktree", "add", "-b", branch,
                 str(target), self._base],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"git worktree add failed: {exc.stderr.decode().strip()}") from exc
        except FileNotFoundError as exc:
            raise ValueError("git not found") from exc
        return str(target)
```

> `runtime_checkable` 讓 `isinstance(x, PaneSender)` 可用（structural），但測試只需把 fake 賦給型別註記變數 + 呼叫方法即可證明相容；不對真實作呼叫副作用方法。

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::SeamProtocolTests -q`
Expected: 1 passed。

---

### Task 4: dispatcher.py（建 worktree→送命令→記 job + 完成偵測）— TDD

**Files:**
- Test: `tests/test_persona_phase2_coordinator_cli.py`（新增 `DispatcherTests`）
- Create: `paulshaclaw/coordinator/dispatcher.py`

- [ ] **Step 1: 寫失敗測試（RED）**

在 `tests/test_persona_phase2_coordinator_cli.py` 插入（沿用 Task 3 的 `FakePaneSender`/`FakeWorktreeCreator`）：

```python
class _RaisingWorktreeCreator:
    def create(self, branch: str) -> str:
        raise ValueError("boom: worktree add failed")


class DispatcherTests(unittest.TestCase):
    def _make(self, tmp: Path):
        from paulshaclaw.coordinator.dispatcher import Dispatcher
        from paulshaclaw.coordinator.registry import JobRegistry

        reg = JobRegistry(state_path=tmp / "jobs.json")
        sender = FakePaneSender()
        creator = FakeWorktreeCreator()
        return Dispatcher(reg, sender, creator), reg, sender, creator

    def test_dispatch_records_job_and_sends_command(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            disp, reg, sender, creator = self._make(Path(d))
            command = 'copilot --model gpt-5.4 --yolo -p "<contract+PROMPT>"'
            job = disp.dispatch(task="slice-a", persona="builder",
                                pane_id="%5", command=command)

            self.assertEqual(job["job_id"], "slice-a-1")
            self.assertEqual(job["status"], "dispatched")
            self.assertEqual(job["pane"], "%5")
            # worktree 被建立、branch 由 task 推導
            self.assertEqual(creator.created, ["feature/slice-a"])
            self.assertEqual(job["worktree"], "/fake/wt/feature-slice-a")
            self.assertEqual(job["branch"], "feature/slice-a")
            # 送入 pane 的文字 = 呼叫者給的 command（一字不差）
            self.assertEqual(sender.sent, [("%5", command)])
            # registry 確實記了
            self.assertEqual(len(reg.list_jobs()), 1)
            self.assertEqual(reg.get_job("slice-a-1")["status"], "dispatched")

    def test_multiple_dispatch_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            disp, reg, sender, creator = self._make(Path(d))
            j1 = disp.dispatch(task="a", persona="builder", pane_id="%1", command="cmd-a")
            j2 = disp.dispatch(task="b", persona="builder", pane_id="%2", command="cmd-b")
            # job_id 用 registry-wide 單調計數器：a→1、b→2（確定性、跨 task 唯一）
            self.assertEqual(j1["job_id"], "a-1")
            self.assertEqual(j2["job_id"], "b-2")
            self.assertEqual({j["job_id"] for j in reg.list_jobs()}, {"a-1", "b-2"})
            self.assertEqual(creator.created, ["feature/a", "feature/b"])
            self.assertEqual(sender.sent, [("%1", "cmd-a"), ("%2", "cmd-b")])

    def test_worktree_failure_records_no_job_and_sends_nothing(self) -> None:
        from paulshaclaw.coordinator.dispatcher import Dispatcher
        from paulshaclaw.coordinator.registry import JobRegistry

        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            sender = FakePaneSender()
            disp = Dispatcher(reg, sender, _RaisingWorktreeCreator())
            with self.assertRaises(ValueError):
                disp.dispatch(task="x", persona="builder", pane_id="%9", command="cmd")
            # fail-closed：不送命令、不記 job
            self.assertEqual(sender.sent, [])
            self.assertEqual(reg.list_jobs(), [])

    def test_poll_done_marks_done_on_new_commit(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            disp, reg, sender, creator = self._make(Path(d))
            job = disp.dispatch(task="c", persona="builder", pane_id="%3", command="cmd-c")
            # baseline head 記在 dispatch 時（fake git_runner 回 baseline）
            # 之後 git_runner 回新 head → 標 done
            new_head_runner = lambda args: "deadbeefcafe"
            updated = disp.poll_done(job["job_id"], git_runner=new_head_runner)
            self.assertEqual(updated["status"], "done")
            self.assertEqual(reg.get_job("c-1")["status"], "done")

    def test_poll_done_no_new_commit_keeps_status(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            disp, reg, sender, creator = self._make(Path(d))
            # dispatch 時以固定 head 記 baseline；poll 回同 head → 維持 dispatched
            disp.dispatch(task="e", persona="builder", pane_id="%4", command="cmd-e",
                          git_runner=lambda args: "samehead")
            updated = disp.poll_done("e-1", git_runner=lambda args: "samehead")
            self.assertEqual(updated["status"], "dispatched")
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::DispatcherTests -q`
Expected: RED，`ModuleNotFoundError: No module named 'paulshaclaw.coordinator.dispatcher'`。

- [ ] **Step 3: 實作 dispatcher.py（GREEN）**

建立 `paulshaclaw/coordinator/dispatcher.py`：

```python
from __future__ import annotations

import subprocess
from typing import Callable

from .registry import JobRegistry
from .seams import PaneSender, WorktreeCreator

# git_runner seam：收 git 參數、回 stdout 文字。預設真實作呼 git。
GitRunner = Callable[[list[str]], str]


def _default_git_runner(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _branch_for_task(task: str) -> str:
    return f"feature/{task}"


class Dispatcher:
    """派工原語：建 worktree → 送命令 → 記 job；poll_done 以 branch 新 commit 標 done。

    所有副作用經注入 seam（PaneSender / WorktreeCreator / git_runner）；
    單元測試注入 fake，不啟動真 tmux/worktree/copilot。
    """

    def __init__(
        self,
        registry: JobRegistry,
        pane_sender: PaneSender,
        worktree_creator: WorktreeCreator,
    ) -> None:
        self._registry = registry
        self._pane_sender = pane_sender
        self._worktree_creator = worktree_creator
        # job_id -> dispatch 當下的 branch head（baseline），供 poll_done 比對
        self._baseline_head: dict[str, str | None] = {}

    def dispatch(
        self,
        *,
        task: str,
        persona: str,
        pane_id: str,
        command: str,
        git_runner: GitRunner | None = None,
    ) -> dict[str, object]:
        branch = _branch_for_task(task)
        # (1) 先建 worktree；失敗則 raise（不送命令、不記 job — fail-closed）
        worktree = self._worktree_creator.create(branch)
        # (2) 忠實轉送呼叫者給的完整 command（本 change 不組裝 copilot 指令）
        self._pane_sender.send(pane_id, command)
        # (3) registry 記一筆 job（status=dispatched）
        job = self._registry.create_job(
            task=task, persona=persona, branch=branch,
            pane=pane_id, worktree=worktree,
        )
        # baseline head（若可取）供 poll_done 比對；取不到記 None
        runner = git_runner or _default_git_runner
        try:
            self._baseline_head[job["job_id"]] = runner(["rev-parse", branch])
        except Exception:
            self._baseline_head[job["job_id"]] = None
        return job

    def poll_done(
        self,
        job_id: str,
        git_runner: GitRunner | None = None,
    ) -> dict[str, object]:
        """branch 出現新 commit（head 異於 baseline）→ 標 done；否則維持原 status。"""
        job = self._registry.get_job(job_id)
        runner = git_runner or _default_git_runner
        try:
            current = runner(["rev-parse", job["branch"]])
        except Exception:
            return job  # 取不到 head → 無法判定，維持原狀
        baseline = self._baseline_head.get(job_id)
        if current != baseline:
            return self._registry.update_status(job_id, "done")
        return job
```

> `dispatch` 在送命令前先建 worktree：worktree 失敗（raise）即冒泡，`send`/`create_job` 不會執行（fail-closed，避免記到沒 worktree 的 job）。`poll_done` 與 `test_poll_done_no_new_commit_keeps_status` 一致：dispatch 與 poll 用同一 fake head → 視為無新 commit → 維持。

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::DispatcherTests -q`
Expected: 5 passed。

---

### Task 5: cli.py + __main__.py（dispatch/jobs/stat，main(argv) 可注入）— TDD

**Files:**
- Test: `tests/test_persona_phase2_coordinator_cli.py`（新增 `CliTests`）
- Create: `paulshaclaw/coordinator/cli.py`、`paulshaclaw/coordinator/__main__.py`

- [ ] **Step 1: 寫失敗測試（RED）**

在 `tests/test_persona_phase2_coordinator_cli.py` 插入（沿用 fakes）：

```python
import contextlib
import io


class CliTests(unittest.TestCase):
    def _fakes(self, tmp: Path):
        from paulshaclaw.coordinator.registry import JobRegistry

        reg = JobRegistry(state_path=tmp / "jobs.json")
        return reg, FakePaneSender(), FakeWorktreeCreator()

    def test_main_dispatch_with_fakes(self) -> None:
        from paulshaclaw.coordinator import cli

        with tempfile.TemporaryDirectory() as d:
            reg, sender, creator = self._fakes(Path(d))
            command = 'copilot --model gpt-5.4 --yolo -p "go"'
            argv = ["dispatch", "--task", "slice-z", "--persona", "builder",
                    "--pane", "%7", "--command", command]
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(argv, registry=reg, pane_sender=sender, worktree_creator=creator)
            self.assertEqual(rc, 0)
            # 送出的命令一字不差
            self.assertEqual(sender.sent, [("%7", command)])
            # registry 多一筆 job 且 stdout 為該 job 的 JSON
            self.assertEqual(len(reg.list_jobs()), 1)
            printed = json.loads(buf.getvalue())
            self.assertEqual(printed["job_id"], "slice-z-1")
            self.assertEqual(printed["pane"], "%7")

    def test_main_jobs_and_stat(self) -> None:
        from paulshaclaw.coordinator import cli

        with tempfile.TemporaryDirectory() as d:
            reg, sender, creator = self._fakes(Path(d))
            cli.main(["dispatch", "--task", "j", "--persona", "builder",
                      "--pane", "%1", "--command", "c"],
                     registry=reg, pane_sender=sender, worktree_creator=creator)

            # jobs：列出既有 job
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["jobs"], registry=reg, pane_sender=sender, worktree_creator=creator)
            self.assertEqual(rc, 0)
            listed = json.loads(buf.getvalue())
            self.assertEqual([j["job_id"] for j in listed], ["j-1"])

            # stat：存在的 job 回 0
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["stat", "j-1"], registry=reg, pane_sender=sender, worktree_creator=creator)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["job_id"], "j-1")

            # stat：不存在的 job 回非零
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = cli.main(["stat", "nope-9"], registry=reg, pane_sender=sender, worktree_creator=creator)
            self.assertNotEqual(rc, 0)
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::CliTests -q`
Expected: RED，`ModuleNotFoundError: No module named 'paulshaclaw.coordinator.cli'`（或 `AttributeError: module ... has no attribute 'main'`）。

- [ ] **Step 3: 實作 cli.py + __main__.py（GREEN）**

建立 `paulshaclaw/coordinator/cli.py`：

```python
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .dispatcher import Dispatcher
from .registry import JobRegistry
from .seams import PaneSender, ScriptWorktreeCreator, TmuxPaneSender, WorktreeCreator


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m paulshaclaw.coordinator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dispatch = sub.add_parser("dispatch", help="派一個 job 進 pane+worktree")
    p_dispatch.add_argument("--task", required=True)
    p_dispatch.add_argument("--persona", required=True)
    p_dispatch.add_argument("--pane", required=True)
    p_dispatch.add_argument("--command", required=True)

    sub.add_parser("jobs", help="列出所有 job")

    p_stat = sub.add_parser("stat", help="查單一 job")
    p_stat.add_argument("job_id")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    registry: JobRegistry | None = None,
    pane_sender: PaneSender | None = None,
    worktree_creator: WorktreeCreator | None = None,
) -> int:
    args = _build_parser().parse_args(argv)

    # 未注入 → 接線真實 seam（CLI 預設行為）；測試一律全注入 fake
    reg = registry if registry is not None else JobRegistry()
    sender = pane_sender if pane_sender is not None else TmuxPaneSender()
    creator = worktree_creator if worktree_creator is not None else ScriptWorktreeCreator()

    if args.cmd == "dispatch":
        disp = Dispatcher(reg, sender, creator)
        job = disp.dispatch(
            task=args.task, persona=args.persona,
            pane_id=args.pane, command=args.command,
        )
        print(json.dumps(job, ensure_ascii=False))
        return 0

    if args.cmd == "jobs":
        print(json.dumps(reg.list_jobs(), ensure_ascii=False))
        return 0

    if args.cmd == "stat":
        try:
            job = reg.get_job(args.job_id)
        except KeyError as exc:
            print(f"錯誤: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(job, ensure_ascii=False))
        return 0

    return 2  # pragma: no cover（argparse required=True 已擋）


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

建立 `paulshaclaw/coordinator/__main__.py`：

```python
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: RED → GREEN**

Run: `python -m pytest tests/test_persona_phase2_coordinator_cli.py::CliTests -q`
Expected: 2 passed。

---

### Task 6: 匯出 + scope 紀律 + 不回歸

**Files:**
- Modify: `paulshaclaw/coordinator/__init__.py`

- [ ] **Step 1: 補全 package 匯出**

把 `paulshaclaw/coordinator/__init__.py` 改為（此時 seams/dispatcher/cli 皆已存在）：

```python
"""Stage4 persona Phase 2 minimal coordinator CLI package."""

from . import cli, dispatcher, registry, seams

__all__ = [
    "registry",
    "seams",
    "dispatcher",
    "cli",
]
```

- [ ] **Step 2: scope 紀律確認（不得改 daemon/config）**

Run: `git diff --name-only main...HEAD -- paulshaclaw/core/daemon.py paulshaclaw/core/config.py`
Expected: **空輸出**（這兩檔本階段未被修改）。若有輸出，回退對應變更。

- [ ] **Step 3: 全套件不回歸**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠，**唯二允許失敗** 為 `tests/test_stage11_operator_cockpit.py` 的 textual/`query_one` 兩筆既知環境失敗；其餘任何失敗皆為真，須回到對應 Task 修。

- [ ] **Step 4: 既有 daemon/coordinator-stub 不回歸**

Run: `python -m pytest tests/test_stage1_smoke.py tests/test_stage1_command_registry.py -q`
Expected: 全綠（本階段未動 daemon/`LocalCoordinator`，行為不變）。

---

### Task 7: 驗證（設計 §11 Phase 2 獨立驗收）

- [ ] **Step 1: openspec 驗證**

Run: `openspec validate persona-phase2-coordinator-cli --strict`
Expected: `Change 'persona-phase2-coordinator-cli' is valid`。

- [ ] **Step 2: package 可 import、CLI 入口存在（不碰真副作用）**

Run:
```bash
python -c "import paulshaclaw.coordinator as c; print(c.__all__)"
python -m paulshaclaw.coordinator --help
python -m paulshaclaw.coordinator jobs --help 2>/dev/null; echo "subcmd ok"
```
Expected: 印出 `['registry', 'seams', 'dispatcher', 'cli']`、`--help` 列出 `dispatch`/`jobs`/`stat` 子命令、退出 0。**不**跑真 `dispatch`（會觸碰 tmux/git worktree）。

- [ ] **Step 3: 確定性 job_id 端到端（fake 注入，設計 §11 Phase 2 獨立驗收）**

Run:
```bash
python - <<'PY'
import tempfile
from pathlib import Path
from paulshaclaw.coordinator.registry import JobRegistry
from paulshaclaw.coordinator.dispatcher import Dispatcher

class FakeSender:
    def __init__(self): self.sent = []
    def send(self, p, t): self.sent.append((p, t))

class FakeWt:
    def create(self, b): return f"/fake/wt/{b.replace('/', '-')}"

with tempfile.TemporaryDirectory() as d:
    reg = JobRegistry(state_path=Path(d) / "jobs.json")
    disp = Dispatcher(reg, FakeSender(), FakeWt())
    j = disp.dispatch(task="demo", persona="builder", pane_id="%1", command="echo hi")
    assert j["job_id"] == "demo-1", j
    assert j["status"] == "dispatched"
    assert reg.get_job("demo-1")["worktree"] == "/fake/wt/feature-demo"
    print("phase2 acceptance ok:", j["job_id"], j["status"])
PY
```
Expected: 印 `phase2 acceptance ok: demo-1 dispatched`（確定性 id、worktree 經 fake 建立、job 記錄；全程無真 tmux/git）。

---

## Done When

- [ ] `paulshaclaw/coordinator/` package 含 `__init__`/`registry`/`seams`/`dispatcher`/`cli`/`__main__` 六檔且 `__init__` 已匯出。
- [ ] `tests/test_persona_phase2_coordinator_cli.py` 四組（`JobRegistryTests`/`SeamProtocolTests`/`DispatcherTests`/`CliTests`）全綠。
- [ ] 全套件 `python -m pytest tests/ paulshaclaw/memory/tests/ -q` 綠（除 2 個既知 stage11 textual 失敗）。
- [ ] `git diff --name-only main...HEAD` **不含** `paulshaclaw/core/daemon.py`、`paulshaclaw/core/config.py`（scope 紀律）。
- [ ] `openspec validate persona-phase2-coordinator-cli --strict` 通過。
- [ ] 測試全程注入 fake，**無**真 copilot/真 tmux/真 git worktree；job_id 確定性（task + 計數器，無時間/亂數）。
- [ ] 全程 local commit、**不 push/不開 PR/不 merge**（由 controller 在 gating 後處理）。
