# Manager Control Plane 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 cockpit（快速鍵）與 paulshiabro（slash command）透過「檔案契約」觀測並觸發 persona manager，manager 改由常駐 daemon（start.sh loop）驅動，前端零 coordinator 耦合。

**Architecture:** 三層——(1) `paulshaclaw/control/` 檔案契約（requests/done/status 於 `~/.agents/control/`）；(2) `paulshaclaw/coordinator/manager_daemon.py` 常駐 loop 排空 request + 週期 idle-gated tick + 寫 status，復用既有 `autonomy`/`manager`/`JobRegistry`；(3) 前端純 controller 只讀 status / 原子寫 request / 查 done。runtime 用 `scripts/start.sh` 的 `start_manager_loop()`（仿 `start_dream_loop`）。

**Tech Stack:** Python 3.12（stdlib：`json`/`os`/`uuid`/`datetime`/`pathlib`）、Textual（cockpit）、pytest。設計依據 `docs/superpowers/specs/2026-07-03-manager-control-plane-design.md`。

**測試指令（全程）：** `~/.local/bin/pytest tests/<file> -v`（memory：`unittest discover` 會漏 `def test(tmp_path)` 風格）。cockpit 行為以 CI 為準，本機做 import/AST/inspect。

---

## File Structure

| 檔案 | 職責 | 動作 |
|---|---|---|
| `paulshaclaw/control/__init__.py` | 新套件 | Create |
| `paulshaclaw/control/paths.py` | control plane 路徑常數（單一來源，#91） | Create |
| `paulshaclaw/control/contract.py` | schema + atomic read/write + request/done/status builders | Create |
| `paulshaclaw/control/client.py` | 前端 API：`read_status`/`submit_request`/`poll_done`（零 coordinator import） | Create |
| `paulshaclaw/coordinator/manager_daemon.py` | `process_request`/`build_status`/`run_once`/`run_loop` | Create |
| `paulshaclaw/cockpit/manager_panel.py` | `ManagerModal`（仿 `help.py`） | Create |
| `paulshaclaw/cockpit/app.py` | 加 `m`/`t` Binding + actions | Modify |
| `paulshaclaw/core/commands.json` | 加 `/manager` | Modify |
| `paulshaclaw/core/daemon.py` | `_handle_manager_command` + 註冊 handler | Modify |
| `scripts/start.sh` | `start_manager_loop()`，取代 timer 掛載 | Modify |
| `tests/test_control_contract.py` | 契約測試 | Create |
| `tests/test_control_client.py` | client 測試 | Create |
| `tests/test_coordinator_manager_daemon.py` | daemon 測試 | Create |
| `tests/test_cockpit_manager_actions.py` | cockpit action/binding 測試 | Create |
| `tests/test_manager_command.py` | `/manager` handler 測試 | Create |
| `tests/test_start_manager_loop.py` | start.sh loop 測試（仿 `test_start_manager_service.py`） | Create |

---

## Task 1: control plane 路徑常數（`paths.py`）

**Purpose:** 給整個 control plane 一個可 env 覆寫、不散落的單一路徑來源；後續所有讀寫都靠它定位（呼應 #91 路徑集中）。

**Files:**
- Create: `paulshaclaw/control/__init__.py`
- Create: `paulshaclaw/control/paths.py`
- Test: `tests/test_control_contract.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_control_contract.py
import os
from paulshaclaw.control import paths


def test_control_root_defaults_under_agents(monkeypatch):
    monkeypatch.delenv("PSC_CONTROL_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/home/tester")
    root = paths.control_root()
    assert str(root) == "/home/tester/.agents/control"


def test_control_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    assert paths.control_root() == tmp_path
    assert paths.requests_dir() == tmp_path / "requests"
    assert paths.done_dir() == tmp_path / "done"
    assert paths.status_file() == tmp_path / "status.json"
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_control_contract.py -v`
Expected: FAIL（`ModuleNotFoundError: paulshaclaw.control`）

- [ ] **Step 3: 最小實作**

```python
# paulshaclaw/control/__init__.py
```
```python
# paulshaclaw/control/paths.py
from __future__ import annotations

import os
from pathlib import Path


def control_root() -> Path:
    override = os.environ.get("PSC_CONTROL_ROOT")
    if override:
        return Path(override)
    return Path(os.environ.get("HOME", str(Path.home()))) / ".agents" / "control"


def requests_dir() -> Path:
    return control_root() / "requests"


def done_dir() -> Path:
    return control_root() / "done"


def status_file() -> Path:
    return control_root() / "status.json"


def lock_file() -> Path:
    return control_root() / "manager.lock"
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_control_contract.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/control/__init__.py paulshaclaw/control/paths.py tests/test_control_contract.py
git commit -m "feat(control): manager control plane 路徑常數"
```

---

## Task 2: 契約 schema + 原子讀寫（`contract.py`）

**Purpose:** 定義 request/done/status 的 schema 與原子讀寫，是前端與 daemon 的共同語言，杜絕半寫檔與格式漂移。

**Files:**
- Create: `paulshaclaw/control/contract.py`
- Test: `tests/test_control_contract.py`（append）

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_control_contract.py（append）
from paulshaclaw.control import contract


def test_atomic_write_and_read_roundtrip(tmp_path):
    target = tmp_path / "x.json"
    contract.atomic_write_json(target, {"a": 1})
    assert contract.read_json(target) == {"a": 1}
    # 寫入後目錄不留 temp 檔
    assert [p.name for p in tmp_path.iterdir()] == ["x.json"]


def test_read_json_missing_returns_none(tmp_path):
    assert contract.read_json(tmp_path / "nope.json") is None


def test_build_request_shape():
    req = contract.build_request("tick", {"executor": "copilot"}, "cockpit")
    assert req["schema_version"] == 1
    assert req["type"] == "tick"
    assert req["args"] == {"executor": "copilot"}
    assert req["requested_by"] == "cockpit"
    assert req["req_id"] and req["created_at"]


def test_build_request_rejects_bad_type():
    import pytest
    with pytest.raises(ValueError):
        contract.build_request("delete-everything", {}, "cockpit")
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_control_contract.py -v`
Expected: FAIL（`AttributeError: module ... has no attribute 'atomic_write_json'`）

- [ ] **Step 3: 最小實作**

```python
# paulshaclaw/control/contract.py
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUEST_TYPES = frozenset({"tick", "fanout"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)  # atomic on同檔系


def read_json(path: Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_request(req_type: str, args: dict[str, Any], requested_by: str) -> dict[str, Any]:
    if req_type not in REQUEST_TYPES:
        raise ValueError(f"unsupported request type: {req_type}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": SCHEMA_VERSION,
        "req_id": f"{stamp}-{uuid.uuid4().hex[:12]}",
        "type": req_type,
        "args": dict(args),
        "requested_by": requested_by,
        "created_at": _utcnow(),
    }


def build_done(req_id: str, status: str, *, result=None, error=None,
               started_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "req_id": req_id,
        "status": status,          # ok | error
        "result": result,
        "error": error,
        "started_at": started_at,
        "finished_at": _utcnow(),
    }
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_control_contract.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/control/contract.py tests/test_control_contract.py
git commit -m "feat(control): 契約 schema 與原子讀寫"
```

---

## Task 3: 前端 client（`client.py`）

**Purpose:** 給前端一支零 coordinator 依賴的薄 API（read_status/submit_request/poll_done）；切 repo（#125）後仍可用。

**Files:**
- Create: `paulshaclaw/control/client.py`
- Test: `tests/test_control_client.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_control_client.py
from paulshaclaw.control import client, contract, paths


def test_submit_request_writes_atomic(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    req_id = client.submit_request("tick", {"executor": "copilot"}, "cockpit")
    written = contract.read_json(paths.requests_dir() / f"{req_id}.json")
    assert written["type"] == "tick"
    assert written["requested_by"] == "cockpit"


def test_read_status_missing_is_degraded(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    status = client.read_status()
    assert status["degraded"] is True
    assert status["ready"] == [] and status["in_flight"] == []


def test_read_status_reads_file(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    contract.atomic_write_json(paths.status_file(), {
        "schema_version": 1, "ready": ["sl-a"], "in_flight": [], "recent_done": [],
        "daemon": {"pid": 1}, "updated_at": "t",
    })
    status = client.read_status()
    assert status["degraded"] is False
    assert status["ready"] == ["sl-a"]


def test_poll_done_returns_none_before_ready(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    assert client.poll_done("req-x", timeout=0.0) is None
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_control_client.py -v`
Expected: FAIL（`ModuleNotFoundError`/`AttributeError`）

- [ ] **Step 3: 最小實作**

```python
# paulshaclaw/control/client.py
from __future__ import annotations

import time
from typing import Any

from . import contract, paths

_DEGRADED = {
    "degraded": True, "ready": [], "in_flight": [], "recent_done": [],
    "daemon": None, "updated_at": None,
}


def submit_request(req_type: str, args: dict[str, Any], requested_by: str) -> str:
    req = contract.build_request(req_type, args, requested_by)
    contract.atomic_write_json(paths.requests_dir() / f"{req['req_id']}.json", req)
    return req["req_id"]


def read_status() -> dict[str, Any]:
    data = contract.read_json(paths.status_file())
    if data is None:
        return dict(_DEGRADED)
    data.setdefault("degraded", False)
    for key in ("ready", "in_flight", "recent_done"):
        data.setdefault(key, [])
    return data


def poll_done(req_id: str, timeout: float = 15.0, interval: float = 0.5) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    path = paths.done_dir() / f"{req_id}.json"
    while True:
        data = contract.read_json(path)
        if data is not None:
            return data
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_control_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/control/client.py tests/test_control_client.py
git commit -m "feat(control): 前端 controller client（read_status/submit/poll，零 coordinator import）"
```

---

## Task 4: daemon 單一 request 處理（`process_request`）

**Purpose:** 把「一個 request → 一個 done」做成 fail-safe 純函式，單一 request 失敗不擴散、可獨立測。

**Files:**
- Create: `paulshaclaw/coordinator/manager_daemon.py`
- Test: `tests/test_coordinator_manager_daemon.py`

參考既有 `paulshaclaw/coordinator/cli.py` 的注入 seam（`main(registry=..., launcher=..., is_satisfied=...)`）與 `manager.run_tick` 簽名。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_coordinator_manager_daemon.py
from paulshaclaw.coordinator import manager_daemon


class _FakeTick:
    """模擬 tick_fn(args)：記錄 args、回固定 summary。"""
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return {"dispatched": ["sl-a"], "polled": [], "completed": [], "errors": []}


def test_process_tick_request_returns_done_ok():
    fake = _FakeTick()
    req = {"schema_version": 1, "req_id": "r1", "type": "tick",
           "args": {"executor": "copilot"}, "requested_by": "cockpit"}
    done = manager_daemon.process_request(req, tick_fn=fake)
    assert done["req_id"] == "r1"
    assert done["status"] == "ok"
    assert done["result"]["dispatched"] == ["sl-a"]
    assert fake.calls == [{"executor": "copilot"}]


def test_process_bad_type_returns_error():
    req = {"schema_version": 1, "req_id": "r2", "type": "nuke", "args": {}, "requested_by": "x"}
    done = manager_daemon.process_request(req, tick_fn=lambda args: {})
    assert done["status"] == "error"
    assert "nuke" in done["error"]


def test_process_tick_failure_captured_as_error():
    def boom(args):
        raise RuntimeError("dispatch exploded")
    req = {"schema_version": 1, "req_id": "r3", "type": "tick", "args": {}, "requested_by": "x"}
    done = manager_daemon.process_request(req, tick_fn=boom)
    assert done["status"] == "error"
    assert "exploded" in done["error"]
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -v`
Expected: FAIL（`ModuleNotFoundError: manager_daemon`）

- [ ] **Step 3: 最小實作**

```python
# paulshaclaw/coordinator/manager_daemon.py
from __future__ import annotations

from typing import Any, Callable

from ..control import contract

TickFn = Callable[[dict[str, Any]], dict]  # tick_fn(args) -> summary


def process_request(req: dict[str, Any], *, tick_fn: TickFn) -> dict[str, Any]:
    """處理單一 control request，回 done payload。永不 raise（fail-safe）。"""
    req_id = req.get("req_id", "unknown")
    req_type = req.get("type")
    if req_type not in contract.REQUEST_TYPES:
        return contract.build_done(req_id, "error", error=f"unsupported request type: {req_type}")
    try:
        summary = tick_fn(req.get("args") or {})
        return contract.build_done(req_id, "ok", result=summary)
    except Exception as exc:  # noqa: BLE001 — loop 不可倒（仿 dream）
        return contract.build_done(req_id, "error", error=f"{type(exc).__name__}: {exc}")
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/coordinator/manager_daemon.py tests/test_coordinator_manager_daemon.py
git commit -m "feat(coordinator): manager daemon 單一 request 處理（fail-safe）"
```

---

## Task 5: daemon 單輪迭代（`run_once`：drain + status）

**Purpose:** 組出可測的單輪心跳（排空 requests + 寫 status 快照），刻意不含無窮迴圈以利單元測試。

**Files:**
- Modify: `paulshaclaw/coordinator/manager_daemon.py`
- Test: `tests/test_coordinator_manager_daemon.py`（append）

`run_once` 不含 `while`/`sleep`（可測）：排空 requests → 寫 done → 寫 status。`build_status` 從注入的 provider 取 ready/in_flight/recent_done。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_coordinator_manager_daemon.py（append）
from paulshaclaw.control import contract, paths


def test_run_once_drains_request_and_writes_done_and_status(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    # 放一個 tick request
    req = contract.build_request("tick", {"executor": "copilot"}, "cockpit")
    contract.atomic_write_json(paths.requests_dir() / f"{req['req_id']}.json", req)

    manager_daemon.run_once(
        tick_fn=lambda args: {"dispatched": ["sl-a"], "polled": [], "completed": [], "errors": []},
        status_provider=lambda: {"ready": ["sl-a"], "in_flight": [], "recent_done": []},
        now="2026-07-03T00:00:00Z",
        pid=999,
    )

    # request 已被消化
    assert list(paths.requests_dir().glob("*.json")) == []
    # done 寫出且 ok
    done = contract.read_json(paths.done_dir() / f"{req['req_id']}.json")
    assert done["status"] == "ok"
    # status 快照寫出
    status = contract.read_json(paths.status_file())
    assert status["ready"] == ["sl-a"]
    assert status["daemon"]["pid"] == 999


def test_run_once_bad_json_request_is_skipped_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    paths.requests_dir().mkdir(parents=True, exist_ok=True)
    (paths.requests_dir() / "garbage.json").write_text("{not json", encoding="utf-8")
    # 不可 raise
    manager_daemon.run_once(
        tick_fn=lambda args: {}, status_provider=lambda: {"ready": [], "in_flight": [], "recent_done": []},
        now="t", pid=1,
    )
    status = contract.read_json(paths.status_file())
    assert status is not None
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -k run_once -v`
Expected: FAIL（`AttributeError: run_once`）

- [ ] **Step 3: 最小實作（append 到 manager_daemon.py）**

```python
# paulshaclaw/coordinator/manager_daemon.py（append）
from . import paths as _unused  # noqa  — 佔位，實際用下方 import
from ..control import contract, paths


def run_once(*, tick_fn, status_provider, now: str, pid: int) -> None:
    """單輪：排空 requests → 寫 done → 寫 status 快照。永不 raise。"""
    req_dir = paths.requests_dir()
    req_dir.mkdir(parents=True, exist_ok=True)
    for req_path in sorted(req_dir.glob("*.json")):
        req = contract.read_json(req_path)
        if req is None:
            req_path.unlink(missing_ok=True)  # 壞檔丟棄，不致命
            continue
        done = process_request(req, tick_fn=tick_fn)
        contract.atomic_write_json(paths.done_dir() / f"{done['req_id']}.json", done)
        req_path.unlink(missing_ok=True)

    snap = status_provider()
    snap.update({
        "schema_version": contract.SCHEMA_VERSION,
        "updated_at": now,
        "daemon": {"pid": pid, "last_tick_at": now, "idle": True},
        "degraded": False,
    })
    contract.atomic_write_json(paths.status_file(), snap)
```

> 註：移除上面佔位 import 行，只保留 `from ..control import contract, paths`。

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/coordinator/manager_daemon.py tests/test_coordinator_manager_daemon.py
git commit -m "feat(coordinator): daemon run_once 排空 request 並寫 status 快照"
```

---

## Task 6: daemon 生產接線（`build_status_provider` + `default_tick_fn` + `run_loop`）

**Purpose:** 把心跳接上真實 coordinator 資料源並包成常駐 `run_loop`（stop 旗標可注入以利測試），完成 daemon 主體。

**Files:**
- Modify: `paulshaclaw/coordinator/manager_daemon.py`
- Test: `tests/test_coordinator_manager_daemon.py`（append）

把 `run_once` 的注入點接到真實 coordinator：`status_provider` 讀 `autonomy.scan_specs`+`ready_units`、`JobRegistry.list_jobs`、`runtime/handoff/*.json`；`tick_fn` 包 `manager.run_tick` + `SubprocessLauncher`。`run_loop` 才有 `while/sleep`（不在單元測試跑）。

- [ ] **Step 1: 寫失敗測試**（只測 provider 純函式與 loop 可注入停止旗標）

```python
# tests/test_coordinator_manager_daemon.py（append）
def test_build_status_provider_shape(monkeypatch, tmp_path):
    # 注入 fake 掃描/registry，驗證 rollup 欄位
    provider = manager_daemon.build_status_provider(
        specs_dir=str(tmp_path),
        list_ready=lambda: ["sl-x"],
        list_jobs=lambda: [{"job_id": "j1", "scope": "sl-x", "state": "running"}],
        list_recent_done=lambda: [{"slice_id": "sl-y", "gate_status": "passed", "at": "t"}],
    )
    snap = provider()
    assert snap["ready"] == ["sl-x"]
    assert snap["in_flight"][0]["job_id"] == "j1"
    assert snap["recent_done"][0]["gate_status"] == "passed"


def test_run_loop_honors_stop_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_CONTROL_ROOT", str(tmp_path))
    ticks = {"n": 0}
    def stop_after_one():
        ticks["n"] += 1
        return ticks["n"] >= 1  # 第一次就停
    manager_daemon.run_loop(
        poll_interval=0.0,
        tick_fn=lambda args: {},
        status_provider=lambda: {"ready": [], "in_flight": [], "recent_done": []},
        now_fn=lambda: "t", pid=1, should_stop=stop_after_one,
    )
    assert ticks["n"] == 1
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -k "provider or loop" -v`
Expected: FAIL（`AttributeError: build_status_provider`）

- [ ] **Step 3: 最小實作（append）**

```python
# paulshaclaw/coordinator/manager_daemon.py（append）
import time as _time

from . import autonomy, manager
from .registry import JobRegistry


def build_status_provider(*, specs_dir, list_ready, list_jobs, list_recent_done):
    def provider():
        return {
            "ready": list(list_ready()),
            "in_flight": [
                {"job_id": j.get("job_id"), "slice_id": j.get("scope"), "state": j.get("state")}
                for j in list_jobs()
                if j.get("state") in {"dispatched", "running"}
            ],
            "recent_done": list(list_recent_done()),
        }
    return provider


def run_loop(*, poll_interval, tick_fn, status_provider, now_fn, pid,
             should_stop=lambda: False) -> None:
    """常駐迴圈；should_stop 供測試注入。單輪失敗不倒（log 交由呼叫端/stderr）。"""
    while True:
        try:
            run_once(tick_fn=tick_fn, status_provider=status_provider, now=now_fn(), pid=pid)
        except Exception:  # noqa: BLE001
            pass  # 仿 dream `|| true`
        if should_stop():
            return
        if poll_interval:
            _time.sleep(poll_interval)
```

> 生產 `main()`：組 `JobRegistry().list_jobs`、`autonomy.scan_specs(specs_dir)`→`ready_units` 的 ready 清單、掃 `runtime/handoff/*.json` 近 N 筆做 `list_recent_done`；`tick_fn` 為 `def default_tick_fn(args): launcher = SubprocessLauncher(args.get("executor", "copilot"), allow_unsafe=args.get("allow_unsafe", False)); return manager.run_tick(Dispatcher(...), metas=autonomy.scan_specs(specs_dir), launcher=launcher, require_idle=True, ...)`——`run_tick` 不吃 `executor`/`allow_unsafe`，故由 `default_tick_fn` 依每個 request 的 `args` 現組 launcher。此 `main()` 為 thin 接線，不需單元測試（由整合 smoke 覆蓋）。

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_coordinator_manager_daemon.py -v`
Expected: 全 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/coordinator/manager_daemon.py tests/test_coordinator_manager_daemon.py
git commit -m "feat(coordinator): daemon status provider 與 run_loop（可注入停止）"
```

---

## Task 7: cockpit `m`/`t` Binding + ManagerModal

**Purpose:** 讓終端操作者一鍵看狀態 / 踢 tick，且 Binding 自動進 `?` help（可發現性）。

**Files:**
- Create: `paulshaclaw/cockpit/manager_panel.py`（仿 `paulshaclaw/cockpit/help.py`）
- Modify: `paulshaclaw/cockpit/app.py:114-121`（BINDINGS）、加 `action_manager_panel`/`action_manager_tick`
- Test: `tests/test_cockpit_manager_actions.py`

**注意**（memory）：cockpit 行為測試以 CI 為準；本機用 import/AST/inspect 驗 Binding 與 method 存在，action 內用注入的 fake client，不真派工、不阻塞 event loop。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_cockpit_manager_actions.py
import inspect
from paulshaclaw.cockpit.app import CockpitApp  # 依現有類名調整


def test_bindings_include_manager_keys():
    keys = {b.key for b in CockpitApp.BINDINGS}
    assert "m" in keys and "t" in keys


def test_manager_actions_exist():
    assert callable(getattr(CockpitApp, "action_manager_panel", None))
    assert callable(getattr(CockpitApp, "action_manager_tick", None))


def test_manager_tick_submits_via_client(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "paulshaclaw.cockpit.app.control_client.submit_request",
        lambda *a, **k: calls.append((a, k)) or "req-1",
    )
    app = CockpitApp.__new__(CockpitApp)          # 免 Textual 全初始化
    app.notify = lambda *a, **k: None             # stub Textual API
    CockpitApp.action_manager_tick(app)
    assert calls and calls[0][0][0] == "tick"
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_cockpit_manager_actions.py -v`
Expected: FAIL（BINDINGS 無 `m`/`t`、無 action）

- [ ] **Step 3: 最小實作**

`paulshaclaw/cockpit/manager_panel.py`（仿 help.py 的 ModalScreen）：
```python
from __future__ import annotations

from textual.screen import ModalScreen
from textual.widgets import Static
from textual.binding import Binding


class ManagerModal(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss_panel", "Close")]

    def __init__(self, status: dict) -> None:
        super().__init__()
        self._status = status

    def compose(self):
        s = self._status
        if s.get("degraded"):
            yield Static("manager: degraded（daemon 未回報 / status.json 缺）")
            return
        ready = ", ".join(s.get("ready") or []) or "—"
        inflight = ", ".join(j["slice_id"] for j in s.get("in_flight") or []) or "—"
        yield Static(f"就緒: {ready}\n在跑: {inflight}\n更新: {s.get('updated_at')}")

    def action_dismiss_panel(self) -> None:
        self.dismiss()
```

`paulshaclaw/cockpit/app.py`：頂部 import
```python
from paulshaclaw.control import client as control_client
from paulshaclaw.cockpit.manager_panel import ManagerModal
```
BINDINGS 內新增（接在 `question_mark` 後）：
```python
        Binding("m", "manager_panel", "m manager 狀態"),
        Binding("t", "manager_tick", "t 踢 manager tick"),
```
新增 actions：
```python
    def action_manager_panel(self) -> None:
        self.push_screen(ManagerModal(control_client.read_status()))

    def action_manager_tick(self) -> None:
        req_id = control_client.submit_request("tick", {"executor": "copilot"}, "cockpit")
        self.notify(f"manager tick 已送出（{req_id[:16]}…）")
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_cockpit_manager_actions.py -v`
Expected: 3 passed（若 Textual 版本致 import 失敗，記錄並以 CI 為準——見 memory）

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/cockpit/manager_panel.py paulshaclaw/cockpit/app.py tests/test_cockpit_manager_actions.py
git commit -m "feat(cockpit): m/t 快速鍵接 manager control plane（自動進 help）"
```

---

## Task 8: paulshiabro `/manager [status|tick]`

**Purpose:** 讓遠端（Telegram）也能觀測 / 觸發 manager，並對齊既有 `/tmate` 子動作指令風格。

**Files:**
- Modify: `paulshaclaw/core/commands.json`（加 `/manager`）
- Modify: `paulshaclaw/core/daemon.py:63-69`（註冊 handler）、加 `_handle_manager_command`
- Test: `tests/test_manager_command.py`

照既有 `/tmate`（`_handle_tmate_command`）子動作模式。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_manager_command.py
import json
from pathlib import Path

from paulshaclaw.core.command_registry import load_command_registry


def test_manager_command_registered():
    reg = load_command_registry(
        Path(__file__).resolve().parents[1] / "paulshaclaw" / "core" / "commands.json"
    )
    spec = reg.get("/manager")
    assert spec.func_call.type == "python"
    assert spec.telegram_menu.command == "manager"


def test_handle_manager_status(monkeypatch):
    from paulshaclaw.core import daemon as daemon_mod
    monkeypatch.setattr(daemon_mod.control_client, "read_status",
                        lambda: {"degraded": False, "ready": ["sl-a"], "in_flight": [], "updated_at": "t"})
    d = daemon_mod.PaulShiaBroDaemon.__new__(daemon_mod.PaulShiaBroDaemon)  # daemon.py:46
    out = daemon_mod.PaulShiaBroDaemon._handle_manager_command(d, ["status"], None)
    assert out["ok"] is True and "sl-a" in out["text"]


def test_handle_manager_tick(monkeypatch):
    from paulshaclaw.core import daemon as daemon_mod
    calls = []
    monkeypatch.setattr(daemon_mod.control_client, "submit_request",
                        lambda *a, **k: calls.append(a) or "req-9")
    monkeypatch.setattr(daemon_mod.control_client, "poll_done", lambda *a, **k: None)
    d = daemon_mod.PaulShiaBroDaemon.__new__(daemon_mod.PaulShiaBroDaemon)
    out = daemon_mod.PaulShiaBroDaemon._handle_manager_command(d, ["tick"], None)
    assert out["ok"] is True
    assert calls and calls[0][0] == "tick"
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_manager_command.py -v`
Expected: FAIL（registry 無 `/manager`、無 handler）

- [ ] **Step 3: 最小實作**

`paulshaclaw/core/commands.json` 於 `commands` 陣列末端加：
```json
    {
      "name": "/manager",
      "usage": "/manager [status|tick]",
      "summary": "觀測 persona manager 狀態或踢一趟 tick",
      "telegram_menu": { "command": "manager", "description": "manager 狀態/tick", "enabled": true },
      "func_call": { "type": "python", "target": "manager" }
    }
```
`paulshaclaw/core/daemon.py` 頂部 import：
```python
from paulshaclaw.control import client as control_client
```
`python_handlers` dict（原 63-69）加一行：
```python
                "manager": self._handle_manager_command,
```
新增 method：
```python
    def _handle_manager_command(self, args: list[str], command) -> dict[str, object]:
        action = args[0] if args else "status"
        if action == "status":
            s = control_client.read_status()
            if s.get("degraded"):
                return {"ok": True, "text": "manager: degraded（daemon 未回報）"}
            ready = ", ".join(s.get("ready") or []) or "—"
            inflight = ", ".join(j["slice_id"] for j in s.get("in_flight") or []) or "—"
            return {"ok": True, "text": f"就緒: {ready}\n在跑: {inflight}\n更新: {s.get('updated_at')}"}
        if action == "tick":
            req_id = control_client.submit_request("tick", {"executor": "copilot"}, "telegram")
            done = control_client.poll_done(req_id, timeout=15.0)
            if done is None:
                return {"ok": True, "text": f"tick 已排入（{req_id[:16]}…），稍後 /manager status 查"}
            if done.get("status") == "ok":
                r = done.get("result") or {}
                return {"ok": True, "text": f"tick 完成：dispatched={r.get('dispatched')} completed={r.get('completed')}"}
            return {"ok": True, "text": f"tick 失敗：{done.get('error')}"}
        raise ValueError("/manager 只接受 status/tick")
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_manager_command.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/core/commands.json paulshaclaw/core/daemon.py tests/test_manager_command.py
git commit -m "feat(paulshiabro): /manager status|tick 接 control plane（照 /tmate 子動作）"
```

---

## Task 9: start.sh `start_manager_loop()`（取代 timer 掛載）

**Purpose:** 用已驗證的 start.sh loop 把 daemon 真的常駐起來，取代 WSL 跑不起的 systemd timer。

**Files:**
- Modify: `scripts/start.sh`（新增 `start_manager_loop`；`start_manager_service` 改為停用/不呼叫 timer；主流程呼叫 `start_manager_loop`）
- Test: `tests/test_start_manager_loop.py`（仿 `tests/test_start_manager_service.py`，對 start.sh 做文字/結構斷言）

**注意**（memory）：start.sh 是 entrypoint，改後需重啟 tmux 生效；本任務只改腳本 + 靜態測試，不在此重啟。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_start_manager_loop.py
from pathlib import Path

START = Path(__file__).resolve().parents[1] / "scripts" / "start.sh"


def test_start_manager_loop_defined_and_called():
    text = START.read_text(encoding="utf-8")
    assert "start_manager_loop()" in text
    # 主流程有呼叫
    assert text.count("start_manager_loop") >= 2
    # 有 toggle 與 log（仿 dream）
    assert "PSC_MANAGER_DAEMON_DISABLED" in text
    assert "manager.log" in text


def test_manager_loop_runs_daemon_module():
    text = START.read_text(encoding="utf-8")
    assert "paulshaclaw.coordinator.manager_daemon" in text
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `~/.local/bin/pytest tests/test_start_manager_loop.py -v`
Expected: FAIL（start.sh 尚無 `start_manager_loop`）

- [ ] **Step 3: 最小實作**（仿 `start_dream_loop`，見 `scripts/start.sh:174-212`）

於 `scripts/start.sh` 新增：
```bash
start_manager_loop() {
  if [[ "${PSC_MANAGER_DAEMON_DISABLED:-0}" == "1" ]]; then
    echo "manager loop disabled (PSC_MANAGER_DAEMON_DISABLED=1)"
    return 0
  fi
  local interval="${PSC_MANAGER_POLL_SECONDS:-5}"
  local manager_log="$HOME/.agents/log/manager.log"
  mkdir -p "$HOME/.agents/log"
  (
    while true; do
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.coordinator.manager_daemon \
        --poll-interval "$interval" >>"$manager_log" 2>&1 || true
      sleep "$interval"
    done
  ) &
  MANAGER_PID=$!
  echo "manager loop pid=$MANAGER_PID (interval=${interval}s)"
}
```
主流程（原 `start_manager_service` 呼叫處，約 287 行）改為呼叫 `start_manager_loop`；`start_manager_service` 本體保留但不再於主流程掛 timer（避免雙重 tick），或加註「systemd 版歸 #126」。`cleanup()` 內補 `kill "$MANAGER_PID" 2>/dev/null || true`。

> `manager_daemon.py` 需補一個 `__main__` 進入點解析 `--poll-interval` 並呼 `run_loop(..., should_stop=lambda: False)`（生產無停止旗標）。此為 thin 接線，靜態測試已覆蓋腳本面。

- [ ] **Step 4: 跑測試確認 pass**

Run: `~/.local/bin/pytest tests/test_start_manager_loop.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/start.sh paulshaclaw/coordinator/manager_daemon.py tests/test_start_manager_loop.py
git commit -m "feat(start): start_manager_loop 常駐 daemon（仿 dream），取代 WSL 跑不起的 timer"
```

---

## Task 10: 全套件回歸 + 契約文件對齊（收尾，不進 CI/PR）

**Purpose:** 確認未破壞既有（`/dispatch`、cockpit pane swap）且文件即契約（#125 前置），封住整條實作。

**Files:**
- Modify: `docs/superpowers/specs/2026-07-03-manager-control-plane-design.md`（如實作偏離則回填契約 schema）
- 可選 Modify: `README.md` / `docs/**`（R-18 docs 對齊，WARN 不擋）

- [ ] **Step 1: 跑相關套件測試**

Run:
```bash
~/.local/bin/pytest tests/test_control_contract.py tests/test_control_client.py \
  tests/test_coordinator_manager_daemon.py tests/test_manager_command.py \
  tests/test_start_manager_loop.py tests/test_cockpit_manager_actions.py -v
```
Expected: 全 passed（cockpit 若受 Textual 版本影響，記錄並以 CI 為準）

- [ ] **Step 2: 確認未破壞既有**

Run: `~/.local/bin/pytest tests/test_coordinator_manager.py tests/test_stage1_command_registry.py tests/test_start_manager_service.py -v`
Expected: 全 passed（既有 /dispatch、manager、start.sh 行為不變）

- [ ] **Step 3: 契約 schema 回填**

若實作中 request/done/status 欄位有調整，更新 spec §4 的 JSON 範例與 `SCHEMA_VERSION`，使文件即契約（#125 前置）。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(control): manager control plane 全套件回歸 + 契約文件對齊"
```

---

## 停止點（依使用者指示）

**本計畫執行到 Task 10 commit 為止即停**：不 push、不開 PR、不進 `openspec-archive` / `requesting-code-review` / `codex:adversarial-review`。後續若要通 CI / 開 PR（`Closes #187`，`feature/manager-control-plane`，zh-TW）與 systemd 化（#126）、前端新增 slice、enforce（#124），另行指示。

## 自我檢核（writing-plans self-review）

- **Spec 覆蓋**：§4 契約→Task1-3；§5 daemon→Task4-6,9；§6.1 cockpit→Task7；§6.2 paulshiabro→Task8；§9 測試策略→各 Task 的 RED + Task10。無遺漏。
- **Placeholder**：各 code 步驟均為可執行內容；`main()`/`__main__` thin 接線明確標為整合覆蓋而非留空。
- **型別一致**：`submit_request(type,args,requested_by)`、`read_status()`、`poll_done(req_id,timeout)`、`process_request(req,*,tick_fn)`、`run_once(*,tick_fn,status_provider,now,pid)`、`run_loop(...,should_stop)`、`build_done(req_id,status,*,result,error,started_at)` 跨 Task 一致。
- **類名已核實**：cockpit `CockpitApp`（`paulshaclaw/cockpit/app.py:109`）、core `PaulShiaBroDaemon`（`paulshaclaw/core/daemon.py:46`）——Task7/8 測試 import 已對齊。`manager.run_tick` 簽名不含 `executor`/`allow_unsafe`（`coordinator/manager.py:136`），故 `tick_fn(args)` 由生產 `default_tick_fn` 依 args 現組 `SubprocessLauncher`。
