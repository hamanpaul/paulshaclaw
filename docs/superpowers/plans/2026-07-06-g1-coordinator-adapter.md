# G1 Coordinator 真 Adapter + Backlog 可見性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **實作者：gpt5.3-codex**。分支 `feature/14-g1-coordinator-adapter`，worktree 隔離，不得在 main。測試：`python3 -m pytest tests/ -q`。
> 依據：`openspec/changes/g1-coordinator-adapter/`＋`docs/superpowers/specs/2026-07-06-g1-coordinator-adapter-design.md`（審查修正版）。

**Goal:** `/dispatch <slice>` 端到端產真 job（五道 fail-closed 檢查＋稽核覆蓋）；held backlog 穿透到 operator；specs_dir 接 repo。

**Architecture:** 擴充既有 control 檔案契約（requests/done/status+lock）第三型別 `dispatch`；bot 端新 `ControlPlaneCoordinator` 走 selection 注入；status held 由 provider→client→daemon 顯示三層穿透。

**Tech Stack:** Python 3.10+、pytest、bash（start.sh）。

**錨點**：`control/contract.py:12`（REQUEST_TYPES frozenset）、`control/client.py:17-43`（read_status 正規化鍵）、`coordinator/manager_daemon.py:157-200`（status provider）＋`build_request_executor`、`bot/listener.py:213-226`（UnavailableCoordinator 注入）、`core/config.py`（CoordinatorSettings）、`core/daemon.py`（_format_manager_status）。

---

### Task 1: 契約層 dispatch 型別

**Files:** Modify `paulshaclaw/control/contract.py`；Test `tests/test_control_contract.py`（既有檔加測試）

- [ ] **Step 1: 失敗測試**

```python
def test_build_dispatch_request():
    req = contract.build_request(req_type="dispatch",
                                 args={"slice_id": "s1", "force_hold": True},
                                 requested_by="telegram:42")
    assert req["type"] == "dispatch" and req["args"]["slice_id"] == "s1"

def test_unknown_type_still_raises():
    with pytest.raises(ValueError):
        contract.build_request(req_type="nope", args={}, requested_by="x")
```

- [ ] **Step 2: RED**（`ValueError: unsupported request type: dispatch`）
- [ ] **Step 3:** `REQUEST_TYPES = frozenset({"tick", "fanout", "dispatch"})`；GREEN
- [ ] **Step 4: Commit** `feat(control): contract 支援 dispatch request 型別`

### Task 2: executor 五道檢查＋派發

**Files:** Modify `paulshaclaw/coordinator/manager_daemon.py`（`build_request_executor` 內加 `type=="dispatch"` 分支）；Test `tests/test_coordinator_manager_daemon.py`

- [ ] **Step 1: 失敗測試**（fake launcher/registry/specs fixture；沿檔內既有 executor 測試慣例）

```python
def test_dispatch_unknown_slice(...):    # done error == "unknown-slice"
def test_dispatch_no_plan(...):          # plan: null → "no-plan"
def test_dispatch_deps_unsatisfied(...): # done error 含 "deps-unsatisfied" 與缺的 dep 名
def test_dispatch_hold_blocked(...):     # dispatch: hold 且無 force_hold → "dispatch-hold"，launcher 未被呼叫
def test_dispatch_force_hold_audited(...):
    # force_hold=True → job 啟動；done 含 {"override": "hold", "requested_by": ...}
def test_dispatch_already_active(...):   # registry 有同 slice dispatched job → "already-active"
def test_dispatch_success(...):          # 全過 → done 含 job_id/worktree/branch/slice_id
```

- [ ] **Step 2: RED → Step 3: 實作**：分支流程＝`scan_specs(args.specs_dir or specs_dir)`→篩 slice→五檢（順序如 spec §3.2；already-active 查 `registry.list_jobs()` 中同 `task` 且 status ∈ IN_FLIGHT_STATUSES）→`_resolve_launcher` 派發→done 寫成功紀錄。
- [ ] **Step 4: GREEN → Commit** `feat(manager): dispatch request 五道 fail-closed 檢查＋稽核覆蓋`

### Task 3: status held 三層穿透

**Files:** Modify `manager_daemon.py`（provider）、`control/client.py`（read_status）、`core/daemon.py`（_format_manager_status）；Test 同上三檔對應測試

- [ ] **Step 1: 失敗測試**：provider——三類 held fixture（no-plan/dispatch-hold/deps-unsatisfied:<dep>）分類正確、與 ready 互斥；client——status.json 帶 held 傳遞、無 held 鍵→[]；daemon——輸出字串含 held 摘要。
- [ ] **Step 2: RED → Step 3: 實作**：provider 在同次 scan 對 ready_units 差集分類；`read_status` 正規化 dict 加 `"held": list(payload.get("held", []))`；`_format_manager_status` 加一行 held 摘要（slice_id＋首因）。
- [ ] **Step 4: GREEN → Commit** `feat(status): held backlog 穿透 provider/client/daemon 顯示`

### Task 4: ControlPlaneCoordinator + backend selection

**Files:** Modify `paulshaclaw/control/client.py`（新 class）、`paulshaclaw/core/config.py`（CoordinatorSettings.backend）、`paulshaclaw/bot/listener.py:213-226`（selection 注入）；Test `tests/test_telegram_listener.py`＋`tests/test_control_client.py`

- [ ] **Step 1: 失敗測試**：`create_job({"slice_id": "s1"})` 寫出合法 request 檔（tmp control root）且回含 req_id；`wait_done(req_id, timeout=0)` 無 done → None；backend 未設 → Unavailable（既有 fail-closed 測試零回歸）；`backend="control"` → 新 adapter；`PSC_COORDINATOR_BACKEND` env 覆寫。
- [ ] **Step 2: RED → Step 3: 實作**：adapter 用既有 `contract.build_request`＋`atomic_write_json`；selection 於 `build_listener`/`build_dispatch_guard_daemon` 注入點；`LocalCoordinator` docstring 加 test-only 標記。
- [ ] **Step 4: GREEN → Commit** `feat(bot): coordinator backend selection＋ControlPlaneCoordinator（fail-closed 預設不變）`

### Task 5: start.sh 接線＋e2e

**Files:** Modify `scripts/start.sh:312` 附近（manager 啟動參數）；Test `tests/test_start_sh_manager*.py`＋新 e2e

- [ ] **Step 1:** start.sh manager 啟動加 `--specs-dir "$REPO/docs/superpowers/specs"`；既有 start.sh 測試同步斷言。
- [ ] **Step 2: e2e 測試**（tmp control root＋fake launcher）：request 寫入→executor 處理→done 真 job_id；同 slice 二連發→第二發 already-active。
- [ ] **Step 3:** 全套件綠 → **Commit**；PR body `Closes #23`、`Refs #14`。

---

**Self-review**：spec 兩 capability（manager-control-plane 6 scenario、stage1-core-runtime 2 scenario）↔ Task 1-5 全覆蓋；五拒絕路徑與稽核欄一致；無 TBD。
