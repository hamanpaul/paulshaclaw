# Persona Manager 完成側 tick（#121）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **TDD：每個 production 改動前先寫 failing test 並看它為正確原因 RED。本地 commit、不 push。**

**Goal:** 把 coordinator 完成側組成一支 `complete_tick`：輪詢 in-flight headless job → 偵測完成 → 寫 `runtime/handoff/<slice>.json`（exit-code 主導 `gate_status`、shadow gate 僅觀測）→ 下一趟 `dispatch_ready` 經 `default_is_satisfied` 釋放下游。

**Architecture:** 新模組 `coordinator/manager.py` 提供純編排函式，reuse `dispatcher.poll_headless_done` / `JobRegistry` / `persona.handoff.write_manifest` / `persona.gate.build_verdict`（observational）/ `autonomy.default_is_satisfied`。CLI 加 `complete` 子命令。合併 tick / systemd / handoff-message schema gate 留 Phase C(#122)。

**Tech Stack:** Python 3.12（stdlib `pathlib`/`datetime`/`json`、`typing.Protocol`）、`unittest`（pytest 跑）。

**設計依據:** `docs/superpowers/specs/2026-06-23-persona-manager-complete-tick-design.md`。

**前置:** 分支 `feature/121-manager-complete-tick` 已開（spec commit `55eb1ac`）。測試自 repo 根：`python -m pytest <path> -v`。**不得碰派工側（`dispatch_ready` / `AgentLauncher`）與互動路徑（`route_to_agent`）。**

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/coordinator/manager.py` | Create | `complete_tick` + `GateRunner` seam + `_default_gate_runner` + `_utcnow` |
| `paulshaclaw/coordinator/cli.py` | Modify | 加 `complete` 子命令 |
| `tests/test_coordinator_manager.py` | Create | 完成側單元測試（done/failed/in-flight/reconciliation/gate/error/idempotent/released） |
| `tests/test_coordinator_cli_complete.py` | Create | `complete` 子命令 smoke |

測試用 `FakeDispatcher`（包真 `JobRegistry` + 腳本化 `poll_headless_done`）驅動完成，免真 subprocess/git。

---

## Task 1: 測試鷹架 + FakeDispatcher + done→manifest（RED→GREEN）

**Files:**
- Create: `tests/test_coordinator_manager.py`
- Create: `paulshaclaw/coordinator/manager.py`

- [ ] **Step 1: 寫 failing test**（建 `tests/test_coordinator_manager.py`）

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from paulshaclaw.coordinator import manager
from paulshaclaw.coordinator.registry import JobRegistry


class FakeDispatcher:
    """包真 JobRegistry；poll_headless_done 依 poll_map 腳本化轉態。"""

    def __init__(self, registry: JobRegistry, poll_map: dict | None = None,
                 raise_on: set | None = None) -> None:
        self._registry = registry
        self._poll_map = poll_map or {}   # job_id -> "done"/"failed"
        self._raise_on = raise_on or set()  # job_id -> 模擬 poll 例外

    def poll_headless_done(self, job_id: str) -> dict:
        if job_id in self._raise_on:
            raise RuntimeError(f"poll 爆炸: {job_id}")
        status = self._poll_map.get(job_id)
        if status is None:
            return self._registry.get_job(job_id)  # 仍在跑
        return self._registry.update_headless_result(
            job_id, status=status, exit_code=0 if status == "done" else 1
        )


def _reg(tmp: str) -> JobRegistry:
    return JobRegistry(state_path=Path(tmp) / "jobs.json")


def _make_job(reg: JobRegistry, slice_id: str, *, status_in_flight: bool = True) -> dict:
    job = reg.create_job(
        task=slice_id, persona="builder", branch=f"feature/{slice_id}",
        pane="", worktree=f"/wt/{slice_id}",
        executor="copilot", session_name=slice_id, pid=4242,
        log_path=f"/logs/{slice_id}.jsonl",
    )
    return job


class CompleteTickDoneTests(unittest.TestCase):
    def test_done_job_writes_passed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-a")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"

            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")

            manifest = json.loads((hdir / "slice-a.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")
            self.assertEqual(manifest["completion"], "done")
            self.assertEqual(manifest["slice_id"], "slice-a")
            self.assertEqual(manifest["completed_at"], "T0")
            self.assertEqual(summary["completed"], [{"slice_id": "slice-a", "gate_status": "passed"}])
            self.assertEqual(summary["errors"], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: FAIL（`ModuleNotFoundError: paulshaclaw.coordinator.manager`）

- [ ] **Step 3: 寫最小實作**（建 `paulshaclaw/coordinator/manager.py`）

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from ..persona import gate, handoff
from . import autonomy

IN_FLIGHT_STATUSES = frozenset({"dispatched", "running"})
TERMINAL_STATUSES = frozenset({"done", "failed"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GateRunner(Protocol):
    def __call__(self, job: dict) -> dict | None: ...


def _default_gate_runner(job: dict) -> dict | None:
    """shadow diff gate（觀測用）。取不到 base/head 或 git 失敗 → None（不阻釋放）。"""
    branch = job.get("branch")
    base = job.get("dispatch_head")
    if not (isinstance(branch, str) and branch and isinstance(base, str) and base):
        return None
    role = job.get("persona") if isinstance(job.get("persona"), str) else "builder"
    try:
        changed = gate.compute_changed_paths(base, branch)
    except Exception:
        return None
    return gate.build_verdict(role=role, changed_paths=changed, manifest_ok=False)


def _satisfied_pred(handoff_dir: str):
    return lambda slice_id: autonomy.default_is_satisfied(slice_id, handoff_dir=handoff_dir)


def complete_tick(
    dispatcher,
    *,
    gate_runner: GateRunner | None = None,
    handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
    metas: list[dict] | None = None,
    clock: Callable[[], str] = _utcnow,
) -> dict:
    registry = dispatcher._registry
    runner = gate_runner if gate_runner is not None else _default_gate_runner
    hdir = Path(handoff_dir)

    polled: list[str] = []
    completed: list[dict] = []
    errors: list[dict] = []

    before_ready: set[str] = set()
    if metas is not None:
        before_ready = {
            m["slice_id"] for m in autonomy.ready_units(metas, _satisfied_pred(handoff_dir))
        }

    for snapshot in registry.list_jobs():
        job_id = snapshot["job_id"]
        try:
            job = snapshot
            status = job.get("status")
            if status in IN_FLIGHT_STATUSES:
                job = dispatcher.poll_headless_done(job_id)
                polled.append(job_id)
                status = job.get("status")

            if status not in TERMINAL_STATUSES:
                continue

            slice_id = job.get("task")
            manifest_path = hdir / f"{slice_id}.json"
            if manifest_path.is_file():
                continue  # 冪等：已寫過

            gate_status = "passed" if status == "done" else "failed"
            try:
                verdict = runner(job)
            except Exception:
                verdict = None

            handoff.write_manifest(
                manifest_path,
                {
                    "slice_id": slice_id,
                    "gate_status": gate_status,
                    "completion": status,
                    "exit_code": job.get("exit_code"),
                    "branch": job.get("branch"),
                    "gate_verdict": verdict,
                    "completed_at": clock(),
                },
            )
            completed.append({"slice_id": slice_id, "gate_status": gate_status})
        except Exception as exc:
            errors.append({"job_id": job_id, "error": str(exc)})

    summary: dict = {"polled": polled, "completed": completed, "errors": errors}
    if metas is not None:
        after_ready = {
            m["slice_id"] for m in autonomy.ready_units(metas, _satisfied_pred(handoff_dir))
        }
        summary["released"] = sorted(after_ready - before_ready)
    return summary
```

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add paulshaclaw/coordinator/manager.py tests/test_coordinator_manager.py
git commit -m "feat(coordinator): #121 complete_tick 完成側骨架（done→passed manifest）

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: failed→failed manifest + in-flight 不終結

**Files:**
- Modify: `tests/test_coordinator_manager.py`

- [ ] **Step 1: 加 failing tests**（在 `_make_job` 下方新增類別）

```python
class CompleteTickFailedAndInFlightTests(unittest.TestCase):
    def test_failed_job_writes_failed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-b")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "failed"})
            hdir = Path(d) / "handoff"

            manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")

            manifest = json.loads((hdir / "slice-b.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "failed")
            self.assertEqual(manifest["completion"], "failed")

    def test_in_flight_job_not_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-c")
            disp = FakeDispatcher(reg, poll_map={})  # 無轉態 → 仍 dispatched
            hdir = Path(d) / "handoff"

            summary = manager.complete_tick(disp, handoff_dir=str(hdir))

            self.assertFalse((hdir / "slice-c.json").exists())
            self.assertEqual(summary["completed"], [])
            self.assertIn(job["job_id"], summary["polled"])
```

- [ ] **Step 2: 跑測試確認 GREEN**（Task 1 實作已涵蓋此行為）

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS（兩新測試皆過；若 fail 表示 Task 1 邏輯有缺，回頭修）

- [ ] **Step 3: commit**

```bash
git add tests/test_coordinator_manager.py
git commit -m "test(coordinator): #121 failed→failed manifest 與 in-flight 不終結

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: reconciliation（終態但缺 manifest 補寫）+ 冪等

**Files:**
- Modify: `tests/test_coordinator_manager.py`

- [ ] **Step 1: 加 failing tests**

```python
class CompleteTickReconcileTests(unittest.TestCase):
    def test_terminal_job_missing_manifest_is_reconciled(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            _make_job(reg, "slice-d")
            # 模擬「前一趟已轉 done 但 manifest 沒寫成」
            reg.update_headless_result("slice-d-1", status="done", exit_code=0)
            disp = FakeDispatcher(reg, poll_map={})  # 不需再 poll
            hdir = Path(d) / "handoff"

            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")

            self.assertTrue((hdir / "slice-d.json").exists())
            self.assertEqual(summary["completed"], [{"slice_id": "slice-d", "gate_status": "passed"}])
            self.assertEqual(summary["polled"], [])  # 終態 job 不再 poll

    def test_idempotent_second_tick_no_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-e")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"

            manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")
            second = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T1")

            manifest = json.loads((hdir / "slice-e.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["completed_at"], "T0")  # 未被覆寫
            self.assertEqual(second["completed"], [])
            self.assertEqual(second["polled"], [])
```

- [ ] **Step 2: 跑測試確認 GREEN**（Task 1 的 reconciliation/冪等分支已涵蓋）

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS

- [ ] **Step 3: commit**

```bash
git add tests/test_coordinator_manager.py
git commit -m "test(coordinator): #121 reconciliation 補寫與 tick 冪等

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: shadow gate 觀測 + gate_runner 例外不擋釋放

**Files:**
- Modify: `tests/test_coordinator_manager.py`

- [ ] **Step 1: 加 failing tests**

```python
class CompleteTickShadowGateTests(unittest.TestCase):
    def test_shadow_gate_verdict_recorded_but_does_not_block(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-f")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            # gate 即使判 ok=False（有越界），done job 仍 passed
            fake_gate = lambda j: {"ok": False, "violations": [{"path": "x", "reason": "out"}],
                                   "handoff_ok": False}

            manager.complete_tick(disp, gate_runner=fake_gate, handoff_dir=str(hdir), clock=lambda: "T0")

            manifest = json.loads((hdir / "slice-f.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")  # exit-code 主導
            self.assertEqual(manifest["gate_verdict"]["ok"], False)  # 觀測如實記錄

    def test_gate_runner_exception_swallowed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "slice-g")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"

            def boom(j):
                raise RuntimeError("gate 爆炸")

            manager.complete_tick(disp, gate_runner=boom, handoff_dir=str(hdir), clock=lambda: "T0")

            manifest = json.loads((hdir / "slice-g.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["gate_status"], "passed")
            self.assertIsNone(manifest["gate_verdict"])
```

- [ ] **Step 2: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS

- [ ] **Step 3: commit**

```bash
git add tests/test_coordinator_manager.py
git commit -m "test(coordinator): #121 shadow gate 觀測且不阻釋放、例外吞掉

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: per-job 例外隔離 + 釋放下游（注入 metas）

**Files:**
- Modify: `tests/test_coordinator_manager.py`

- [ ] **Step 1: 加 failing tests**

```python
class CompleteTickErrorAndReleaseTests(unittest.TestCase):
    def test_per_job_poll_error_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            a = _make_job(reg, "slice-h")
            b = _make_job(reg, "slice-i")
            disp = FakeDispatcher(reg, poll_map={b["job_id"]: "done"},
                                  raise_on={a["job_id"]})
            hdir = Path(d) / "handoff"

            summary = manager.complete_tick(disp, handoff_dir=str(hdir), clock=lambda: "T0")

            self.assertTrue((hdir / "slice-i.json").exists())   # b 仍完成
            self.assertFalse((hdir / "slice-h.json").exists())  # a 失敗、未寫
            self.assertEqual(summary["completed"], [{"slice_id": "slice-i", "gate_status": "passed"}])
            self.assertEqual([e["job_id"] for e in summary["errors"]], [a["job_id"]])

    def test_downstream_released_after_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            up = _make_job(reg, "up")
            disp = FakeDispatcher(reg, poll_map={up["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            metas = [
                {"slice_id": "up", "dispatch": "auto", "plan": "p-up.md", "depends_on": []},
                {"slice_id": "down", "dispatch": "auto", "plan": "p-down.md", "depends_on": ["up"]},
            ]

            summary = manager.complete_tick(
                disp, handoff_dir=str(hdir), metas=metas, clock=lambda: "T0"
            )

            self.assertIn("down", summary["released"])
            # 完成側落地後，default_is_satisfied 認得 up → down 就緒
            from paulshaclaw.coordinator import autonomy
            self.assertTrue(autonomy.default_is_satisfied("up", handoff_dir=str(hdir)))
```

- [ ] **Step 2: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS

- [ ] **Step 3: commit**

```bash
git add tests/test_coordinator_manager.py
git commit -m "test(coordinator): #121 per-job 例外隔離與下游釋放觀測

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: CLI `complete` 子命令 + smoke

**Files:**
- Modify: `paulshaclaw/coordinator/cli.py`
- Create: `tests/test_coordinator_cli_complete.py`

- [ ] **Step 1: 寫 failing test**（建 `tests/test_coordinator_cli_complete.py`）

```python
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from paulshaclaw.coordinator import cli
from paulshaclaw.coordinator.registry import JobRegistry
from paulshaclaw.coordinator.seams import PaneSender, WorktreeCreator


class _FakeSender(PaneSender):
    def send(self, *a, **k):  # pragma: no cover - complete 不會用到
        raise AssertionError("complete 不應送 pane")


class _FakeCreator(WorktreeCreator):
    def create(self, *a, **k):  # pragma: no cover
        raise AssertionError("complete 不應建 worktree")


class CliCompleteTests(unittest.TestCase):
    def test_complete_subcommand_writes_manifest_and_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            # 終態但缺 manifest → complete 應 reconcile 補寫（dispatch_head=None 免 git）
            reg.create_job(task="slice-cli", persona="builder", branch="feature/slice-cli",
                           pane="", worktree="/wt/slice-cli", executor="copilot",
                           session_name="slice-cli", pid=1, log_path="/l.jsonl")
            reg.update_headless_result("slice-cli-1", status="done", exit_code=0)
            hdir = Path(d) / "handoff"

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(
                    ["complete", "--handoff-dir", str(hdir)],
                    registry=reg, pane_sender=_FakeSender(), worktree_creator=_FakeCreator(),
                )

            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["completed"], [{"slice_id": "slice-cli", "gate_status": "passed"}])
            self.assertTrue((hdir / "slice-cli.json").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_coordinator_cli_complete.py -v`
Expected: FAIL（argparse 不認得 `complete` → SystemExit 2）

- [ ] **Step 3: 改 cli.py**

在頂部 import 加 `manager`：

```python
from . import autonomy, manager
```

在 `_build_parser()` 的 `p_fanout` 區塊後、`return parser` 前加：

```python
    p_complete = sub.add_parser(
        "complete",
        help="完成側 tick：輪詢 in-flight job → 寫 handoff manifest → 釋放下游",
    )
    p_complete.add_argument("--handoff-dir", default=autonomy.DEFAULT_HANDOFF_DIR)
    p_complete.add_argument(
        "--specs-dir", default=None,
        help="設定後據 dependency graph 觀測算出本趟釋放的下游（released）",
    )
```

在 `main()` 的 `if args.cmd in ("ready", "fanout"):` 區塊**之前**加：

```python
    if args.cmd == "complete":
        disp = Dispatcher(reg, sender, creator)
        metas = autonomy.scan_specs(args.specs_dir) if args.specs_dir else None
        summary = manager.complete_tick(disp, handoff_dir=args.handoff_dir, metas=metas)
        print(json.dumps(summary, ensure_ascii=False))
        return 0
```

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_cli_complete.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add paulshaclaw/coordinator/cli.py tests/test_coordinator_cli_complete.py
git commit -m "feat(coordinator): #121 CLI complete 子命令（完成側 tick 入口）

Refs #121

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: 全套件驗證

**Files:** 無（驗證）

- [ ] **Step 1: 跑 coordinator + persona 相關套件**

Run: `python -m pytest tests/test_coordinator_manager.py tests/test_coordinator_cli_complete.py tests/test_coordinator_cli.py tests/test_coordinator_registry_headless.py tests/test_persona_phase4_fanout_autonomy.py -v`
Expected: 全 PASS（確認未回歸派工側/autonomy）

- [ ] **Step 2: 跑完整 test suite 確認無回歸**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全 PASS（基線 ~1198 passing 不減）

- [ ] **Step 3: 若全綠，進 requesting-code-review / codex:adversarial-review gate**（見下方 Execution Handoff 後續）

---

## Self-Review

- **Spec coverage：** §4.1 `complete_tick`→Task 1；§4.2 資料流（in-flight poll / reconciliation / 冪等）→Task 1-3；§4.3 manifest 形狀→Task 1；§4.4 CLI→Task 6；§5 錯誤處理（per-job 隔離、gate 例外、fail-closed failed）→Task 4-5；§6 測試 1-9 全覆蓋；釋放下游觀測→Task 5。無遺漏。
- **Placeholder scan：** 無 TBD/TODO；每個 code step 附完整程式碼與預期輸出。
- **Type consistency：** `complete_tick(dispatcher, *, gate_runner, handoff_dir, metas, clock)` 全檔一致；manifest 鍵（`slice_id/gate_status/completion/exit_code/branch/gate_verdict/completed_at`）與 spec §4.3 一致；CLI 用 `manager.complete_tick(disp, handoff_dir=, metas=)` 與簽名相符；`FakeDispatcher` 暴露 `_registry` + `poll_headless_done` 與真 `Dispatcher` 介面一致。
