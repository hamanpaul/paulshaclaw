---
dispatch: hold
slice_id: persona-manager-complete-tick
plan: null
depends_on: [persona-manager-phase-b]
---

# Persona Manager 完成側 tick（#121）設計

> 日期：2026-06-23 ｜ 狀態：草案（待覆審）｜ 分支：`feature/121-manager-complete-tick`
> 上游：`2026-06-22-persona-manager-daemon-design.md`（umbrella §4.3）、`2026-06-22-persona-manager-phase-b-headless-dispatch-design.md`。
> Issue：#121（umbrella #14 的基石票）。

## 1. 背景與校正

Phase B（#112）已做**派工側**：`autonomy.dispatch_ready` 算就緒集（`dispatch:auto ∧ 有 plan ∧ depends_on 全滿足`），對每個就緒單位經 headless `AgentLauncher` 啟動 agent，並由 `JobRegistry` 記 `executor/session_name/pid/log_path`。

umbrella §4.3 的完整 tick 還含**完成側**：`poll_headless_done → 跑 gate → 寫 runtime/handoff/<slice>.json → 釋放下游 depends_on`。這條**目前不在任何 loop 裡跑**，所以 fan-out 的相依推進不會自己前進——派出去的 job 跑完後沒人把 handoff manifest 寫出來，下一趟 `dispatch_ready` 的 `default_is_satisfied` 永遠看不到 `gate_status=='passed'`，下游卡死。

§4.3 原文以 `PaneAllocator` + pane 為前提；Phase B 已改 headless（subprocess + sentinel），`PaneAllocator` 不存在。本設計把**完成側**落在 headless 世界，並守住 #121 的邊界。

## 2. 目標與非目標

**目標**
- 新增 `paulshaclaw/coordinator/manager.py`，提供一支純編排函式 `complete_tick(...)`：輪詢 in-flight job → 偵測完成 → 寫 completion manifest → 使下一趟 `dispatch_ready` 能釋放下游。
- 新增 CLI `coordinator complete` 子命令作為手動／Phase C timer 的入口。
- 全部 reuse 既有積木，零重造邏輯。

**非目標（明確留給後續票）**
- ❌ 合併 `fanout`+`complete` 成單一 `tick()` 入口、systemd timer、`--require-idle`——Phase C（#122）。
- ❌ builder→reviewer 的 handoff **訊息** schema gate（`validate_handoff_message` 作為釋放依據）——Phase C ② gate。
- ❌ failed job 的 retry / requeue。
- ❌ 動派工側（`dispatch_ready` / `AgentLauncher`）與互動路徑（`route_to_agent`）。

## 3. 釋放判定來源（#104 決策）

`autonomy.py:13` 註明 depends_on 滿足的判定來源（merged-to-main vs handoff gate_status）為 #104 留開放。本票採 **exit-code 主導 + shadow gate**：

- `gate_status = 'passed' if completion=='done' else 'failed'`，completion 由既有 `classify_completion`（exit code + 末筆 JSONL）決定。
- persona diff gate（`persona.gate.build_verdict`）以 **shadow** 跑：結果存入 manifest 的 `gate_verdict` 觀測欄位，**永不改 `gate_status`**，不擋釋放。對齊 Phase B「gate 仍 shadow」定位，且無需 agent 端額外吐 artifact。
- merged-to-main 來源仍可日後換注入物（`default_is_satisfied` / `ready_units` 已收注入 predicate），介面不變。

## 4. 組件設計

### 4.1 `complete_tick`（新純編排函式）

```
complete_tick(dispatcher, *,
              gate_runner: GateRunner | None = None,
              handoff_dir: str = autonomy.DEFAULT_HANDOFF_DIR,
              metas: list[dict] | None = None,
              clock: Callable[[], str] = _utcnow) -> dict
```

`metas` 為**可選**：傳入時（呼叫者已 `scan_specs`）才據 dependency graph 觀測算出本趟新被釋放的下游 `released`；不傳則 `released` 省略。釋放本身不靠此欄位——它由寫出的 manifest + 下一趟 `dispatch_ready` 隱性達成。

reuse：`dispatcher.poll_headless_done`、`dispatcher._registry.list_jobs`、`persona.handoff.write_manifest`、`persona.gate.build_verdict`（observational）、`autonomy.DEFAULT_HANDOFF_DIR`、`coordinator.completion.classify_completion`（已被 `poll_headless_done` 內部用）。

`GateRunner` = 可注入 seam，預設跑 shadow `build_verdict`；單元測試注入 fake，免真 git diff。`clock` 注入以求 `completed_at` 決定性。

### 4.2 單趟資料流

1. **work set** = `list_jobs()` 中
   - status ∈ {`dispatched`, `running`}（in-flight），**∪**
   - status ∈ {`done`, `failed`} 但 `runtime/handoff/<slice>.json` 缺檔者（**reconciliation**：補救「狀態已終態但 manifest 未寫」的 crash 中斷，否則下游永遠卡住）。
2. 對 in-flight job：`dispatcher.poll_headless_done(job_id)` → 可能轉 `done` / `failed`（registry 已持久化狀態）。
3. 對每個（本趟新終態 ∪ reconciliation）job：
   - `slice_id = job["task"]`（Phase B 以 `task=slice_id` 記 job）。
   - `gate_status = 'passed' if job.status=='done' else 'failed'`。
   - shadow gate：best-effort 跑 `gate_runner`；任何例外吞掉，`gate_verdict=None`。
   - `handoff.write_manifest(Path(handoff_dir)/f"{slice_id}.json", manifest)`。
4. 回 summary：`{"polled": [...job_id], "completed": [{slice_id, gate_status}], "errors": [{job_id, error}]}`；若注入 `metas` 另附 `"released": [...下游 slice]`（完成後重算 `ready_units` 與本趟前的差集，純觀測，不在本函式派工）。

### 4.3 completion manifest 形狀

寫至 `runtime/handoff/<slice>.json`（= `autonomy.default_is_satisfied` 讀的同一路徑，§4.3 step 3 指定）：

```json
{
  "slice_id": "persona-manager-phase-c",
  "gate_status": "passed",
  "completion": "done",
  "exit_code": 0,
  "branch": "feature/persona-manager-phase-c",
  "gate_verdict": {"ok": false, "violations": [], "handoff_ok": false},
  "completed_at": "2026-06-23T00:00:00+00:00"
}
```

> **術語界線**：此為**「完成 manifest」**——唯一被 `default_is_satisfied` 依賴的欄位是 `gate_status`。它與 builder→reviewer 的 handoff **訊息**（`contract.validate_handoff_message` schema）是兩種不同 artifact；後者屬 Phase C ② gate，本票不產也不驗。兩者共用 `runtime/handoff/` 目錄但語意不同，設計上以 `gate_status` 欄位區隔。

### 4.4 CLI `coordinator complete`

`cli.py` 加 `complete` 子命令：建 `JobRegistry` + `Dispatcher` → 跑 `complete_tick` → `print(json.dumps(summary))`。與既有 `ready` / `fanout` 子命令同構。

## 5. 錯誤處理（fail-closed）

- 單 job poll 出錯 → 收進 `errors`、其他 job 照跑（per-job 隔離，比照 `dispatch_ready`）。
- 進程死無 sentinel → `poll_headless_done` 已回 `failed` → `gate_status='failed'` → 下游維持封鎖。
- `gate_runner` 拋例外 → 吞掉、`gate_verdict=None`，`gate_status` 仍由 completion 決定。
- manifest 寫入 reuse `handoff.write_manifest`（mkdir + write）。
- reconciliation 確保中斷不致使下游永遠卡死。
- 壞狀態檔由 `JobRegistry._load` 既有 fail-closed raise 處理，不在本層重複。

## 6. 測試（TDD，先 RED）

`tests/test_coordinator_manager.py`：

1. done job → 寫 `runtime/handoff/<slice>.json`，`gate_status=='passed'`、`completion=='done'`。
2. failed job → `gate_status=='failed'`。
3. in-flight（仍存活）job → 不終結、不寫 manifest。
4. 寫檔後 `autonomy.default_is_satisfied(dep)` 回 True，且 `ready_units` 納入原本被該 dep 卡住的下游。
5. reconciliation：job 已 `done` 但 manifest 缺檔 → 本趟補寫。
6. shadow gate 即使 `verdict.ok==False`，done job 仍 `gate_status=='passed'`（gate 不擋釋放）；`gate_verdict` 如實記錄。
7. `gate_runner` 拋例外 → 不影響 `gate_status`，`gate_verdict==None`。
8. tick 重跑冪等：第二趟不重複寫／不報錯。
9. 單 job poll 拋例外 → 進 `errors`、其他 job 仍完成。

`tests/test_coordinator_cli.py`（或既有 CLI 測試）：`complete` 子命令 smoke——印出合法 summary JSON、exit 0。

## 7. 影響檔案

| 檔案 | 動作 | 責任 |
|---|---|---|
| `paulshaclaw/coordinator/manager.py` | Create | `complete_tick` + `GateRunner` seam + `_utcnow` |
| `paulshaclaw/coordinator/cli.py` | Modify | 加 `complete` 子命令 |
| `tests/test_coordinator_manager.py` | Create | 完成側單元測試（§6 1–9） |
| `tests/test_coordinator_cli.py` | Modify/Create | `complete` 子命令 smoke |

純新增 + CLI 一個子命令，不改派工側既有行為。
