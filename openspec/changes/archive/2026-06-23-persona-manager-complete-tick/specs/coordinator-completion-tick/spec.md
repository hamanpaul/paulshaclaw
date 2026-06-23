## ADDED Requirements

### Requirement: complete_tick 輪詢完成並寫 completion manifest

`coordinator-completion-tick` SHALL 提供 `manager.complete_tick(dispatcher, *, gate_runner=None, handoff_dir=autonomy.DEFAULT_HANDOFF_DIR, metas=None, clock=_utcnow)`。對 `dispatcher._registry.list_jobs()` 中 status ∈ `{dispatched, running}` 的 in-flight job，MUST 呼叫 `dispatcher.poll_headless_done(job_id)` 偵測完成。對偵測為終態（`done`/`failed`）且 `runtime/handoff/<slice>.json` 尚未存在的 job，MUST 寫出 completion manifest 至 `handoff_dir/<slice_id>.json`（`slice_id = job["task"]`），含鍵 `slice_id`、`gate_status`、`completion`、`exit_code`、`branch`、`gate_verdict`、`completed_at`。`gate_status` MUST 為 `'passed'`（當 `completion=='done'`）或 `'failed'`（當 `completion=='failed'`）。函式 MUST 回 summary dict，含 `polled`、`completed`（`[{slice_id, gate_status}]`）、`errors`。

#### Scenario: done job 寫 passed manifest

- **WHEN** in-flight job 經 `poll_headless_done` 轉為 `done` 後執行 `complete_tick`
- **THEN** `runtime/handoff/<slice>.json` MUST 被寫出且 `gate_status=='passed'`、`completion=='done'`，summary `completed` MUST 含該 slice

#### Scenario: failed job 寫 failed manifest

- **WHEN** job 轉為 `failed` 後執行 `complete_tick`
- **THEN** manifest 的 `gate_status` MUST 為 `'failed'`，下游 `depends_on` MUST NOT 因此被釋放

#### Scenario: in-flight job 不終結不寫檔

- **WHEN** `poll_headless_done` 回報 job 仍 `dispatched`（未完成）
- **THEN** MUST NOT 寫 manifest，summary `completed` MUST 不含該 slice，`polled` MUST 含該 job_id

### Requirement: 釋放判定採 exit-code 主導且 shadow gate 僅觀測

`complete_tick` 決定 `gate_status` 時 MUST 以完成分類（`done`/`failed`，源自既有 `classify_completion`）為準。注入或預設的 `gate_runner`（persona diff gate）MUST 以 shadow 方式執行：其結果 MUST 存入 manifest 的 `gate_verdict` 欄位作觀測，MUST NOT 改變 `gate_status`、MUST NOT 阻擋釋放。`gate_runner` 拋出例外時 MUST 被吞掉，`gate_verdict` 記為 `null`，`gate_status` 仍由完成分類決定。寫出 `gate_status=='passed'` 的 manifest 後，`autonomy.default_is_satisfied(slice_id, handoff_dir=...)` MUST 回 `True`。

#### Scenario: shadow gate 判 ok=False 仍不擋 done job

- **WHEN** 注入的 `gate_runner` 對一個 `done` job 回 `{"ok": False, ...}`
- **THEN** manifest 的 `gate_status` MUST 仍為 `'passed'`，且 `gate_verdict` MUST 如實記錄該 verdict

#### Scenario: gate_runner 例外不影響 gate_status

- **WHEN** 注入的 `gate_runner` 對 `done` job 拋例外
- **THEN** `gate_status` MUST 為 `'passed'`、`gate_verdict` MUST 為 `null`、manifest MUST 仍寫出

#### Scenario: 完成側落地後釋放下游

- **WHEN** 上游 slice `up` 完成寫出 `gate_status=='passed'` 的 manifest，且傳入含 `down`（`depends_on: ["up"]`）的 `metas`
- **THEN** summary `released` MUST 含 `down`，且 `autonomy.default_is_satisfied("up", handoff_dir=...)` MUST 回 `True`

### Requirement: reconciliation、冪等與 per-job 例外隔離

`complete_tick` 的 work set MUST 含「status 已為終態（`done`/`failed`）但 `runtime/handoff/<slice>.json` 缺檔」的 job 並補寫其 manifest（reconciliation）。同一 slice 已存在 manifest 時 MUST NOT 覆寫（冪等）。單一 job 的輪詢或寫入若拋例外，MUST 收進 summary `errors`（`[{job_id, error}]`）並繼續處理其他 job，MUST NOT 中斷整趟。

#### Scenario: 終態但缺 manifest 被補寫

- **WHEN** registry 中某 job 已 `done` 但其 manifest 不存在，執行 `complete_tick`
- **THEN** 該 manifest MUST 被補寫、summary `completed` MUST 含該 slice，且該已終態 job MUST NOT 再被 `poll`（不出現在 `polled`）

#### Scenario: tick 重跑冪等

- **WHEN** 連續執行 `complete_tick` 兩趟（第一趟已寫出某 slice 的 manifest）
- **THEN** 第二趟 MUST NOT 覆寫該 manifest（`completed_at` 不變）、其 `completed` 與 `polled` MUST NOT 再含該 slice

#### Scenario: 單 job 例外隔離

- **WHEN** 一個 job 的 `poll_headless_done` 拋例外、另一個 job 正常完成
- **THEN** 正常 job 的 manifest MUST 被寫出，出錯 job MUST 進 `errors` 且其 manifest MUST NOT 被寫出
