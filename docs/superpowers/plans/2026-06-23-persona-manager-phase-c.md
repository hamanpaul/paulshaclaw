# Persona Manager Phase C — systemd 常駐 manager（#122）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **TDD：每個 production 改動前先寫 failing test 並看它為正確原因 RED。本地 commit、不 push。**

**Goal:** 把 manager 包成 systemd `--user` timer + oneshot，週期跑完整 tick（fanout→complete，idle-gated）；`start.sh` 退成 toggle。

**Architecture:** Unit A 新增 `manager.run_tick`（reuse `dispatch_ready` + `complete_tick` + `memory.dream.idle`）+ CLI `tick`；Unit B 新增 3 個 systemd 範本並納入 deploy planner；Unit C `start.sh` 加 `start_manager_service()`（graceful skip）+ `install-manager-units.sh`。

**Tech Stack:** Python 3.12（stdlib `os`/`subprocess`）、bash、systemd `--user`、`unittest`（pytest 跑）。

**設計依據:** `docs/superpowers/specs/2026-06-23-persona-manager-phase-c-systemd-design.md`。

**前置:** 分支 `feature/122-phase-c-systemd` 已開（off main，含 #121）。測試自 repo 根：`python -m pytest <path> -v`。**不動互動路徑（`route_to_agent`）。**

---

## File Structure

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/coordinator/manager.py` | Modify | 加 `import os`、`from ..memory.dream import idle`、`run_tick` |
| `paulshaclaw/coordinator/cli.py` | Modify | 加 `tick` 子命令 |
| `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.service.tmpl` | Create | oneshot service |
| `paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.timer.tmpl` | Create | timer |
| `paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl` | Create | manager runtime env |
| `paulshaclaw/deploy/planner.py` | Modify | `_TEMPLATE_CATALOG` += 3 |
| `scripts/start.sh` | Modify | `start_manager_service()` + cleanup stop |
| `scripts/coordinator/install-manager-units.sh` | Create | render→copy→enable |
| `tests/test_coordinator_manager.py` | Modify | `run_tick` 測試 |
| `tests/test_coordinator_cli_tick.py` | Create | CLI `tick` smoke |
| `tests/test_stage7_deploy_three_plane.py` | Modify | manager 範本斷言 |
| `tests/test_start_manager_service.py` | Create | start.sh 函式 bash smoke |

---

## Task 1: `manager.run_tick`（Unit A）

**Files:** Modify `paulshaclaw/coordinator/manager.py`、`tests/test_coordinator_manager.py`

- [ ] **Step 1: 寫 failing tests** — append 到 `tests/test_coordinator_manager.py`（複用既有 `FakeDispatcher`/`_reg`/`_make_job`）：

```python
class RunTickTests(unittest.TestCase):
    def test_skips_when_not_idle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "x")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            summary = manager.run_tick(
                disp, metas=[], require_idle=True, max_load=1.0,
                idle_probe=lambda: (99.0, 99.0, 99.0), handoff_dir=str(hdir), clock=lambda: "T0",
            )
            self.assertEqual(summary["skipped"], "not-idle")
            self.assertEqual(summary["completed"], [])
            self.assertFalse((hdir / "x.json").exists())

    def test_runs_complete_when_idle(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "y")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            summary = manager.run_tick(
                disp, metas=[], require_idle=True, max_load=1.0,
                idle_probe=lambda: (0.0, 0.0, 0.0), handoff_dir=str(hdir), clock=lambda: "T0",
            )
            self.assertFalse(summary["skipped"])
            self.assertEqual(summary["completed"], [{"slice_id": "y", "gate_status": "passed"}])
            self.assertTrue((hdir / "y.json").exists())

    def test_fanout_failure_does_not_block_complete(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = _reg(d)
            job = _make_job(reg, "done-slice")
            disp = FakeDispatcher(reg, poll_map={job["job_id"]: "done"})
            hdir = Path(d) / "handoff"
            # 一個就緒單位但無 launcher → fanout raise RequiresLauncher，收進 errors
            metas = [{"slice_id": "ready-one", "dispatch": "auto", "plan": "p.md", "depends_on": []}]
            summary = manager.run_tick(
                disp, metas=metas, launcher=None, is_satisfied=lambda s: True,
                handoff_dir=str(hdir), clock=lambda: "T0",
            )
            self.assertFalse(summary["skipped"])
            self.assertTrue(any(e.get("stage") == "fanout" for e in summary["errors"]))
            self.assertEqual(summary["completed"], [{"slice_id": "done-slice", "gate_status": "passed"}])
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_coordinator_manager.py::RunTickTests -v`
Expected: FAIL（`AttributeError: module ... has no attribute 'run_tick'`）

- [ ] **Step 3: 實作 run_tick** — 在 `manager.py`：頂部 import 區加 `import os`，並在 `from . import autonomy` 後加 `from ..memory.dream import idle`。檔末加：

```python
def run_tick(
    dispatcher,
    *,
    metas: list[dict],
    launcher=None,
    persona: str = "builder",
    is_satisfied=None,
    gate_runner: GateRunner | None = None,
    handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
    require_idle: bool = False,
    max_load: float = 1.0,
    idle_probe: Callable[[], tuple] = os.getloadavg,
    clock: Callable[[], str] = _utcnow,
) -> dict:
    """跑完整 manager tick：fanout（dispatch_ready）→ complete_tick。

    require_idle 時以 1-min load average gate（reuse memory.dream.idle，可注入 probe）。
    fanout 例外（DispatchReadyError / RequiresLauncher / ValueError 環）收進 errors，
    MUST 仍跑 complete（派工側失敗不阻完成側）。
    """
    if require_idle and not idle.is_idle(max_load=max_load, probe=idle_probe):
        return {"skipped": "not-idle", "dispatched": [], "completed": [], "errors": []}
    satisfied = is_satisfied if is_satisfied is not None else _satisfied_pred(handoff_dir)
    dispatched: list = []
    errors: list = []
    try:
        dispatched = autonomy.dispatch_ready(
            metas, satisfied, dispatcher, persona=persona, launcher=launcher
        )
    except (
        autonomy.DispatchReadyError,
        autonomy.DispatchReadyRequiresLauncherError,
        ValueError,
    ) as exc:
        errors.append({"stage": "fanout", "error": str(exc)})
    complete = complete_tick(
        dispatcher, gate_runner=gate_runner, handoff_dir=handoff_dir, metas=metas, clock=clock
    )
    return {
        "skipped": False,
        "dispatched": dispatched,
        "completed": complete["completed"],
        "errors": errors + complete["errors"],
    }
```

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_manager.py -v`
Expected: PASS（原 12 + 3 = 15）

- [ ] **Step 5: commit**

```bash
git add paulshaclaw/coordinator/manager.py tests/test_coordinator_manager.py
git commit -m "feat(coordinator): #122 manager.run_tick（fanout→complete，idle-gated）

Refs #122

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: CLI `tick` 子命令（Unit A）

**Files:** Modify `paulshaclaw/coordinator/cli.py`、Create `tests/test_coordinator_cli_tick.py`

- [ ] **Step 1: 寫 failing test** — 建 `tests/test_coordinator_cli_tick.py`：

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
    def send(self, *a, **k):  # pragma: no cover
        raise AssertionError("tick 不應送 pane")


class _FakeCreator(WorktreeCreator):
    def create(self, *a, **k):  # pragma: no cover
        raise AssertionError("tick 不應建 worktree")


class CliTickTests(unittest.TestCase):
    def test_tick_idle_skip_prints_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            reg = JobRegistry(state_path=Path(d) / "jobs.json")
            specs = Path(d) / "specs"
            specs.mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                # --max-load=-1：load(>=0) <= -1 恒為 False → 必 not-idle（決定性）
                rc = cli.main(
                    ["tick", "--specs-dir", str(specs), "--require-idle", "--max-load=-1"],
                    registry=reg, pane_sender=_FakeSender(), worktree_creator=_FakeCreator(),
                )
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["skipped"], "not-idle")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_coordinator_cli_tick.py -v`
Expected: FAIL（argparse 不認得 `tick` → SystemExit 2）

- [ ] **Step 3: 改 cli.py** — 在 `_build_parser()` 的 `p_complete` 區塊後、`return parser` 前加：

```python
    p_tick = sub.add_parser(
        "tick",
        help="完整 manager tick：fanout→complete（idle-gated）",
    )
    p_tick.add_argument("--specs-dir", required=True)
    p_tick.add_argument("--persona", default="builder")
    p_tick.add_argument("--executor", choices=sorted(_ARGV_BUILDERS), default=None)
    p_tick.add_argument("--handoff-dir", default=autonomy.DEFAULT_HANDOFF_DIR)
    p_tick.add_argument("--require-idle", action="store_true")
    p_tick.add_argument("--max-load", type=float, default=1.0)
```

在 `main()` 的 `if args.cmd == "complete":` 區塊後加：

```python
    if args.cmd == "tick":
        disp = Dispatcher(reg, sender, creator)
        metas = autonomy.scan_specs(args.specs_dir)
        active_launcher = launcher
        if active_launcher is None and args.executor is not None:
            active_launcher = SubprocessLauncher(executor=args.executor)
        predicate = is_satisfied if is_satisfied is not None else autonomy.default_is_satisfied
        summary = manager.run_tick(
            disp, metas=metas, launcher=active_launcher, persona=args.persona,
            is_satisfied=predicate, handoff_dir=args.handoff_dir,
            require_idle=args.require_idle, max_load=args.max_load,
        )
        print(json.dumps(summary, ensure_ascii=False))
        return 0
```

(`manager` 已於 Task 6/#121 在 cli.py import；確認頂部有 `from . import autonomy, manager`，若無則補。)

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_coordinator_cli_tick.py -v`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add paulshaclaw/coordinator/cli.py tests/test_coordinator_cli_tick.py
git commit -m "feat(coordinator): #122 CLI tick 子命令（完整 tick 入口）

Refs #122

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: systemd 範本 + planner catalog（Unit B）

**Files:** Create 3 範本、Modify `paulshaclaw/deploy/planner.py`、`tests/test_stage7_deploy_three_plane.py`

- [ ] **Step 1: 建 3 個範本**

`paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.service.tmpl`：
```ini
[Unit]
Description=__INSTANCE__ persona manager tick (oneshot)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=PSC_MANAGER_SPECS_DIR=%h/.agents/specs
EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__.env
EnvironmentFile=%h/.agents/core/runtime/__INSTANCE__-manager.env
Environment=PSC_STAGE1_CONFIG=%h/.agents/state/config/__INSTANCE__.state.json
ExecStart=/usr/bin/env python3 -m paulshaclaw.coordinator tick --require-idle --specs-dir ${PSC_MANAGER_SPECS_DIR} --executor ${PSC_MANAGER_EXECUTOR}
```

`paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.timer.tmpl`：
```ini
[Unit]
Description=__INSTANCE__ persona manager tick timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=300
Unit=__INSTANCE__-manager.service

[Install]
WantedBy=timers.target
```

`paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl`：
```ini
PSC_INSTANCE=__INSTANCE__
PSC_PLANE=core
PSC_MANAGER_EXECUTOR=copilot
PSC_MANAGER_INTERVAL_SECONDS=300
```

- [ ] **Step 2: 寫 failing test** — append class 到 `tests/test_stage7_deploy_three_plane.py`：

```python
class ManagerUnitCatalogTests(unittest.TestCase):
    def test_manager_units_present_and_rename(self) -> None:
        assets = list_template_assets()
        relpaths = {a.template_relpath for a in assets}
        for rp in (
            "core/systemd/__INSTANCE__-manager.service.tmpl",
            "core/systemd/__INSTANCE__-manager.timer.tmpl",
            "core/runtime/__INSTANCE__-manager.env.tmpl",
        ):
            self.assertIn(rp, relpaths)

        svc = next(a for a in assets if a.template_relpath == "core/systemd/__INSTANCE__-manager.service.tmpl")
        svc_text = svc.template_path.read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", svc_text)
        self.assertIn("-m paulshaclaw.coordinator tick", svc_text)

        timer = next(a for a in assets if a.template_relpath == "core/systemd/__INSTANCE__-manager.timer.tmpl")
        timer_text = timer.template_path.read_text(encoding="utf-8")
        self.assertIn("OnUnitActiveSec", timer_text)
        self.assertIn("WantedBy=timers.target", timer_text)

        env = next(a for a in assets if a.template_relpath == "core/runtime/__INSTANCE__-manager.env.tmpl")
        self.assertIn("PSC_MANAGER_EXECUTOR=", env.template_path.read_text(encoding="utf-8"))

        target = resolve_template_target("core/systemd/__INSTANCE__-manager.service.tmpl", "demo-agent")
        self.assertEqual(target, "core/systemd/demo-agent-manager.service")
```

- [ ] **Step 3: 跑測試確認 RED**

Run: `python -m pytest tests/test_stage7_deploy_three_plane.py::ManagerUnitCatalogTests -v`
Expected: FAIL（catalog 尚無 manager 範本 → `StopIteration`/`AssertionError`）

- [ ] **Step 4: 改 planner.py** — 在 `_TEMPLATE_CATALOG` 內、`core/runtime/__INSTANCE__-telegram.env.tmpl` 條目之後加：

```python
    (
        "core",
        "core/systemd/__INSTANCE__-manager.service.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/systemd/__INSTANCE__-manager.timer.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
    (
        "core",
        "core/runtime/__INSTANCE__-manager.env.tmpl",
        "以 __INSTANCE__ 取代實例名，並移除 .tmpl 後綴",
    ),
```

- [ ] **Step 5: 跑測試確認 GREEN（含既有 stage7 測試不回歸）**

Run: `python -m pytest tests/test_stage7_deploy_three_plane.py -v`
Expected: PASS（既有 `assertGreaterEqual(len(assets), 7)` 仍成立，數量增加）

- [ ] **Step 6: commit**

```bash
git add paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.service.tmpl \
        paulshaclaw/deploy/templates/core/systemd/__INSTANCE__-manager.timer.tmpl \
        paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl \
        paulshaclaw/deploy/planner.py tests/test_stage7_deploy_three_plane.py
git commit -m "feat(deploy): #122 manager systemd 範本納入三分部署 catalog

Refs #122

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: start.sh toggle + install 腳本（Unit C）

**Files:** Modify `scripts/start.sh`、Create `scripts/coordinator/install-manager-units.sh`、Create `tests/test_start_manager_service.py`

- [ ] **Step 1: 寫 failing test** — 建 `tests/test_start_manager_service.py`（抽出函式以 stub systemctl 跑）：

```python
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
START_SH = REPO / "scripts" / "start.sh"

# 抽出 start_manager_service 函式單獨跑（避免 source 整支 start.sh 的副作用）
_HARNESS = r"""
set -euo pipefail
fn="$(sed -n '/^start_manager_service()/,/^}/p' "{start_sh}")"
eval "$fn"
start_manager_service
"""


def _run(stub_dir: Path, env: dict) -> subprocess.CompletedProcess:
    script = _HARNESS.format(start_sh=str(START_SH))
    full_env = {**os.environ, "PATH": f"{stub_dir}:{os.environ['PATH']}", **env}
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=full_env)


def _write_stub(d: Path, name: str, body: str) -> None:
    p = d / name
    p.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    p.chmod(0o755)


class StartManagerServiceTests(unittest.TestCase):
    def test_disabled_skips(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            _write_stub(sd, "systemctl", 'echo "SYSTEMCTL $*" >> "$0.log"\nexit 0\n')
            res = _run(sd, {"PSC_MANAGER_DISABLED": "1", "PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("disabled", res.stdout)
            self.assertFalse((sd / "systemctl.log").exists())  # 完全沒呼叫 systemctl

    def test_no_systemctl_graceful_skip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)  # 空 stub dir，但 PATH 仍含系統路徑；用假 systemctl 模擬「--user 不可用」
            _write_stub(sd, "systemctl", 'if [[ "$1 $2" == "--user show-environment" ]]; then exit 1; fi\nexit 0\n')
            res = _run(sd, {"PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("skipped", res.stderr + res.stdout)

    def test_starts_timer(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            sd = Path(d)
            log = sd / "calls.log"
            _write_stub(sd, "systemctl", f'echo "$*" >> "{log}"\nexit 0\n')
            res = _run(sd, {"PSC_INSTANCE": "demo"})
            self.assertEqual(res.returncode, 0, res.stderr)
            calls = log.read_text(encoding="utf-8") if log.exists() else ""
            self.assertIn("--user start demo-manager.timer", calls)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑測試確認 RED**

Run: `python -m pytest tests/test_start_manager_service.py -v`
Expected: FAIL（`start_manager_service` 尚不存在 → sed 抽出空字串、`eval` 後呼叫未定義函式）

- [ ] **Step 3: 改 scripts/start.sh** — 在 `start_dream_loop` 定義之後（檔案上半部函式區）加：

```bash
# Phase C: persona manager tick via systemd --user timer. start.sh 不擁有 manager
# 進程，只 toggle；systemctl --user 不可用（WSL 無 user systemd）→ graceful skip。
# 停用：PSC_MANAGER_DISABLED=1。
start_manager_service() {
  if [[ "${PSC_MANAGER_DISABLED:-0}" == "1" ]]; then
    echo "manager service disabled (PSC_MANAGER_DISABLED=1)"
    return 0
  fi
  local instance="${PSC_INSTANCE:-paulshaclaw}"
  if ! command -v systemctl >/dev/null 2>&1 || ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "manager service skipped: systemctl --user unavailable (WSL no user systemd?)" >&2
    return 0
  fi
  if systemctl --user start "${instance}-manager.timer"; then
    echo "manager timer started (${instance}-manager.timer)"
  else
    echo "manager timer start failed (non-fatal)" >&2
  fi
  return 0
}
```

在 `start_dream_loop` 的呼叫處附近（如 `start_dream_loop` 那行之後）加一行 `start_manager_service`。並在 `cleanup()` 內既有 kill 邏輯後加：

```bash
  systemctl --user stop "${PSC_INSTANCE:-paulshaclaw}-manager.timer" 2>/dev/null || true
```

- [ ] **Step 4: 跑測試確認 GREEN**

Run: `python -m pytest tests/test_start_manager_service.py -v`
Expected: PASS（3 tests）

- [ ] **Step 5: 建 install 腳本** `scripts/coordinator/install-manager-units.sh`：

```bash
#!/usr/bin/env bash
# 安裝 persona manager systemd --user units（render→copy→daemon-reload→enable）。
# 用法：install-manager-units.sh [instance] [interval_seconds]
set -euo pipefail

INSTANCE="${1:-${PSC_INSTANCE:-paulshaclaw}}"
INTERVAL="${2:-${PSC_MANAGER_INTERVAL_SECONDS:-300}}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TPL="$REPO/paulshaclaw/deploy/templates/core/systemd"
UNIT_DIR="$HOME/.config/systemd/user"
RUNTIME_DIR="$HOME/.agents/core/runtime"

mkdir -p "$UNIT_DIR" "$RUNTIME_DIR" "$HOME/.agents/specs"

render() {  # $1=template $2=target ; 替 __INSTANCE__、覆寫 OnUnitActiveSec、移除 .tmpl 已由呼叫端定檔名
  sed -e "s/__INSTANCE__/${INSTANCE}/g" \
      -e "s/^OnUnitActiveSec=.*/OnUnitActiveSec=${INTERVAL}/" \
      "$1" > "$2"
}

render "$TPL/__INSTANCE__-manager.service.tmpl" "$UNIT_DIR/${INSTANCE}-manager.service"
render "$TPL/__INSTANCE__-manager.timer.tmpl"   "$UNIT_DIR/${INSTANCE}-manager.timer"
render "$REPO/paulshaclaw/deploy/templates/core/runtime/__INSTANCE__-manager.env.tmpl" \
       "$RUNTIME_DIR/${INSTANCE}-manager.env"

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable --now "${INSTANCE}-manager.timer"
  echo "installed + enabled ${INSTANCE}-manager.timer (interval=${INTERVAL}s)"
else
  echo "units rendered but systemctl --user unavailable; 需在有 user systemd 的 session 內 enable" >&2
fi

if command -v loginctl >/dev/null 2>&1 && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
  echo "提示：開機自啟需 'loginctl enable-linger $USER'（WSL 尤需）" >&2
fi
```

設可執行：`chmod +x scripts/coordinator/install-manager-units.sh`。

- [ ] **Step 6: commit**

```bash
chmod +x scripts/coordinator/install-manager-units.sh
git add scripts/start.sh scripts/coordinator/install-manager-units.sh tests/test_start_manager_service.py
git commit -m "feat(ops): #122 start.sh manager toggle + install-manager-units.sh

Refs #122

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 全套件驗證 + 收尾

**Files:** 無（驗證）

- [ ] **Step 1: coordinator + persona + deploy 套件**

Run: `python -m pytest tests/test_coordinator_manager.py tests/test_coordinator_cli_tick.py tests/test_coordinator_cli_complete.py tests/test_stage7_deploy_three_plane.py tests/test_start_manager_service.py -v`
Expected: 全 PASS

- [ ] **Step 2: 完整 suite 無回歸**

Run: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 較 #121 基線多出本票新測試、無新失敗（既有 `test_stage11_operator_cockpit` 2 失敗為本地缺 requirements-stage11 依賴的環境假象，CI 綠）。

- [ ] **Step 3: WSL `--user` lingering 手動驗證項（文件化，不阻 PR）** — 記於 PR：`scripts/coordinator/install-manager-units.sh` 跑後 `systemctl --user list-timers | grep manager`、`journalctl --user -u <instance>-manager.service` 應有 tick log；開機自啟需 `loginctl enable-linger`。

---

## Self-Review

- **Spec coverage：** coordinator-tick（run_tick idle skip / idle 跑 / fanout 不擋）→Task 1；coordinator-cli（tick 子命令）→Task 2；stage7（manager 範本 catalog + oneshot/timer 內容 + rename）→Task 3。錯誤處理（fanout 失敗收 errors）→Task 1 test。start.sh graceful skip→Task 4。無遺漏。
- **Placeholder scan：** 無 TBD/TODO；每 code step 附完整內容與預期輸出。
- **Type consistency：** `run_tick(...)` 簽名與 spec/Task 1/Task 2 一致；summary 鍵 `skipped/dispatched/completed/errors` 一致；`is_idle(max_load=, probe=)` 與 idle.py 一致；CLI `tick` 參數與 handler 一致；範本 relpath/target 與 planner catalog、stage7 test 一致；install 腳本 render 規則與 planner rename 一致。
