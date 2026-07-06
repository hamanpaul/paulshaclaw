---
dispatch: hold
slice_id: g4-complete-tick-idempotency
plan: null
depends_on: []
---

# G4 — complete_tick manifest idempotency（requeue 可重入） 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#132
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`。

## 1. 背景與問題

`paulshaclaw/coordinator/manager.py` `complete_tick` 的冪等判準是 `if manifest_path.is_file(): continue`——以 `slice_id` 為唯一 key。同一 slice retry/requeue 後的第二輪 job 到達 terminal 時，manifest 已存在 → 新結果**永遠寫不進去**：第一輪 fail 的 `gate_status: failed` 卡死下游（`default_is_satisfied` 讀同檔），重跑成功也無法釋放依賴。

## 2. 目標與非目標

**目標**：requeue 後新 run 的結果能落地；真冪等（同一 job 重掃不重寫）保留；消費端契約不變。
**非目標**：manifest 檔名/位置變更（`runtime/handoff/<slice_id>.json` 不動——`default_is_satisfied`、`recent_done_provider` 等消費端零改）；重試策略本身（屬 dispatcher/registry 語意）。

## 3. 設計

### 3.1 manifest 內容擴充
- 寫入時加 `"job_id": <registry job_id>`（既有欄位 `slice_id`/`gate_status`/`completed_at` 不動；additive）。

### 3.2 冪等規則（`complete_tick` 迴圈內）
manifest 已存在時讀出既有 `job_id` 比對當前 terminal job：
1. **同 `job_id`** → skip（真冪等：同一 run 重掃不重寫，現行語意保留）。
2. **不同 `job_id`** → **overwrite**（新 run 勝：gate_status／verdict／completed_at 全重算重寫）——requeue 解卡的核心。
3. **manifest 壞檔／缺 `job_id`**（舊格式或損毀）→ overwrite（fail-safe：無法證明同 run 即視為舊帳，新結果勝；舊格式檔一次性自然升級）。

### 3.3 邊界
- 同 slice 併發兩 job 同時 terminal：後掃到者勝（順序由 registry.list_jobs 確定性序決定）；此為既有「一 slice 一活躍 job」慣例下的理論案例，測試釘住行為即可，不加鎖（YAGNI）。
- `released` 觀測（before/after ready 差集）語意不變——overwrite 造成 gate_status failed→passed 時，本輪 released 正確反映新解鎖。

## 4. 測試

- 同 job_id 重跑 complete_tick → manifest mtime/內容不變（skip 路徑）。
- requeue 情境：job A fail 寫 manifest（failed）→ 同 slice job B done → complete_tick 後 manifest job_id==B、gate_status==passed；`default_is_satisfied` 由 False 轉 True。
- 舊格式 manifest（無 job_id）＋新 terminal job → overwrite。
- 壞 JSON manifest → overwrite、不 raise。
- 既有 complete_tick 測試零回歸（含 released 觀測、_is_safe_slice_id 拒絕路徑）。

## 5. 風險

- overwrite 抹掉第一輪失敗證據：job 級歷史仍完整在 registry/log（manifest 本就是「最新裁決」快照，非審計日誌）；如需歷史，registry 為真相源——寫入 design 註記即可。
