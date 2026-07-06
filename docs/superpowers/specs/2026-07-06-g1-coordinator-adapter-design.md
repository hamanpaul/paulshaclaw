---
dispatch: hold
slice_id: g1-coordinator-adapter
plan: null
depends_on: []
---

# G1 — coordinator 真 adapter + backlog 可見性 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#14（epic 主體）、#23（/dispatch 文件）
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`（方向已核可：擴充既有 control 契約，不造第二條 queue）

## 1. 背景與問題

真 coordinator（dispatcher/registry/autonomy/launcher，2.1k LOC）建好但未接進 live runtime：bot `/dispatch` 綁 `UnavailableCoordinator`（fail-closed stub）、`core/daemon.py` 預設 `LocalCoordinator`（counter 假 job id）。同時 manager 的 `status.json` 只回報 `ready`，對「有 spec/plan 但未就緒」全隱形——operator 看不到 backlog。

## 2. 目標與非目標

**目標**：`/dispatch <slice_id>` 端到端產真 job；manager status 呈現 held backlog（含原因）；spec 掃描接上 repo 真相源。
**非目標**：persona enforce（G2）；自動 fanout 策略調整（既有 `tick`/`fanout` 語意不動）；production spec 翻 `dispatch:auto`（各 workstream 自行決定）。

## 3. 設計

### 3.1 契約擴充（`paulshaclaw/control/contract.py:12`）
- `REQUEST_TYPES` 加 `"dispatch"`；request args＝`{"slice_id": str, "specs_dir": str | 缺省}`。
- done 紀錄（`done/<req_id>.json`）成功時帶 `{"job_id", "worktree", "branch", "slice_id"}`；失敗帶 `{"error", "reason"}`。additive，`schema_version` 不 bump；既有 consumer（cockpit/status 讀者）對未知 type 的 done 檔不誤讀（相容測試）。

### 3.2 dispatch 執行語意（manager_daemon request executor）
- 處理 `type=="dispatch"`：`scan_specs(args.specs_dir or 啟動值)` → 取 `slice_id` 該筆 meta：
  1. 查無該 slice → done: error `unknown-slice`。
  2. `plan` 空 → done: error `no-plan`（fail-closed：無計畫不派）。
  3. `depends_on` 未全滿足 → done: error `deps-unsatisfied`，列缺的 dep（fail-closed）。
  4. **`dispatch: hold` 預設也擋人令**（review 修正：與 autonomy「只認字面 auto」的 fail-safe 哲學一致）→ done: error `dispatch-hold`。明確覆蓋須 request args 帶 `"force_hold": true`（bot 端 `/dispatch <slice> --force-hold`），且成功 done 紀錄含稽核欄 `{"override": "hold", "requested_by": <caller>}`——覆蓋是**顯式、留痕**的，不是預設。
  5. **active-job guard**：該 slice 已有 in-flight（`dispatched`/`running`）job → done: error `already-active`（fail-closed；terminal 後重下即 requeue）。此守衛維持「一 slice 一活躍 job」不變量——**G4 overwrite 正確性的前提**。
  6. 通過 → 經既有 headless launcher（`_resolve_launcher` 同 fanout 路徑）開 job → done: 成功紀錄。
- 併發與冪等沿既有 request 檔案協定（req_id 唯一、done 檔冪等寫入）。

### 3.3 bot 端 backend selection
- `CoordinatorSettings` 加 `backend: str | None`（config 欄位，env 覆寫 `PSC_COORDINATOR_BACKEND`）。
- 未設 → 現狀 `UnavailableCoordinator`（fail-closed 不變）；`"control"` → 新 **`ControlPlaneCoordinator`**（`paulshaclaw/control/client.py` 側新增）：`create_job(payload)` = `build_request(type="dispatch", args={"slice_id": payload["slice_id"]})` → `atomic_write_json(requests/)` → 立即回 `req_id`；提供 `wait_done(req_id, timeout)` 查 done 檔（`/dispatch` 回覆先回 req_id，done 後由既有 relay/status 面呈現）。
- `LocalCoordinator` docstring 標 test-only，production 選擇邏輯拒用。

### 3.4 backlog 可見性（`manager_daemon.build_runtime_status_provider` → 端到端）
- `status.json` 加 `held: [{"slice_id", "reasons": ["no-plan" | "dispatch-hold" | "deps-unsatisfied:<dep>"]}]`（additive）。
- 來源＝同一次 `scan_specs` 結果對 `ready_units` 三條件的差集分類；無 slice_id 的檔案不列（無身分）。
- **穿透消費端（review 修正——否則 operator 永遠看不到）**：`control/client.py read_status()` 正規化鍵加 `held`（舊 status.json 無此鍵 → 空 list）；`core/daemon._format_manager_status()`（Telegram `/manager status`）顯示 held 摘要（slice_id＋首因）。相容測試：舊格式 status.json → held=[] 不炸；舊讀者對新欄位不誤讀。
- cockpit 呈現面仍為後續小 change（非本件 DoD）；但 client/daemon 這條主要 operator 路徑**在本件內**。

### 3.5 specs_dir 接線（start.sh）
- manager 啟動參數加 `--specs-dir "$REPO/docs/superpowers/specs"`——spec 真相源在 repo、版控可追；不 sync 副本到 `~/.agents/specs/`（複製漂移是既知坑型）。`~/.agents/specs/` 保留為 default（未帶參數時行為不變）。

## 4. 測試

- 契約：`build_request("dispatch")` 合法；未知 type 仍 raise；done 紀錄 schema 測試（含 override 稽核欄）。
- executor：五條拒絕路徑（unknown-slice/no-plan/deps-unsatisfied/**dispatch-hold**/**already-active**）＋ `force_hold` 覆蓋成功且 done 帶稽核欄；launcher 注入 fake。
- adapter：`ControlPlaneCoordinator.create_job` 寫出合法 request 檔並回 req_id；`wait_done` 讀 done。
- selection：backend 未設 → Unavailable（既有 fail-closed 測試零回歸）；`"control"` → 新 adapter。
- status：held 分類三原因各一 fixture；ready/held 互斥；**read_status 傳遞 held**、舊格式相容（held=[]）；`/manager status` 輸出含 held。
- e2e（DoD）：`/dispatch <slice>` → requests → manager 處理 → done 含真 job_id → worktree 建立；同 slice 二連發 → 第二發 `already-active`。

## 5. 風險

- hold 覆蓋面：預設 fail-closed＋顯式 `--force-hold` 留痕稽核（review 修正後），誤派/被入侵遠端亂派的面收斂為「須明碼帶 force 旗標且全程留痕」；G2 enforce 上線後再加 write_paths 硬欄。
- status additive 欄位：舊讀者忽略未知 key（現有 consumer 皆 dict.get 風格，相容測試把關）；read_status/daemon 顯示已納本件。
