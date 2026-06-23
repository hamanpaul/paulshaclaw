# coordinator-tick Specification

## Purpose
TBD - created by archiving change persona-manager-phase-c. Update Purpose after archive.
## Requirements
### Requirement: run_tick 跑 fanout→complete，idle 只擋 fanout

`coordinator-tick` SHALL 提供 `manager.run_tick(dispatcher, *, metas, launcher, persona="builder", is_satisfied=None, gate_runner=None, handoff_dir=autonomy.DEFAULT_HANDOFF_DIR, require_idle=False, max_load=1.0, idle_probe=os.getloadavg, clock=_utcnow)`。當 `require_idle` 為真且 `memory.dream.idle.is_idle(max_load, idle_probe)` 為假時，MUST 跳過 fanout（不派新工）但 MUST 仍執行 `complete_tick`——完成側為便宜的回收/記帳，不得被 idle 埋住（否則高負載時 job 完成/失敗與下游釋放狀態變陳舊）。否則 MUST 先跑 fanout（`autonomy.dispatch_ready`）再跑 `complete_tick`。MUST 回 `{"dispatch_skipped": "not-idle"|False, "dispatched": [...], "completed": [...], "errors": [...]}`。

#### Scenario: idle 未達跳過 fanout 但仍完成回收

- **WHEN** `require_idle=True` 且注入的 `idle_probe` 回報高 load（超過 `max_load`）
- **THEN** summary `dispatch_skipped` MUST 為 `'not-idle'`、`dispatched` MUST 為空，且既有已完成 job 的 handoff manifest MUST 仍被 `complete_tick` 寫出（`completed` 反映之）

#### Scenario: idle 達標跑 fanout + complete

- **WHEN** `require_idle=True` 且 `idle_probe` 回報低 load
- **THEN** `dispatch_skipped` MUST 為 `False`，且完成側結果反映於 `completed`

### Requirement: 同一 slice 不被重複派工（冪等）

`run_tick` 派工前 MUST 跳過 registry 中已有 `dispatched`/`running` job 的 slice_id，避免 oneshot service + timer 反覆對同一就緒 slice 重派（維持一 slice 一 job 不變量）。

#### Scenario: in-flight slice 不重派

- **WHEN** registry 已有某 slice 的 `dispatched` job，且該 slice 在 metas 中為就緒（`dispatch:auto ∧ plan ∧ deps 滿足`）
- **THEN** `run_tick` MUST NOT 對該 slice 再啟動 launcher，`dispatched` MUST 不含該 slice

### Requirement: fanout 失敗不連累 complete

`run_tick` 內 fanout 拋出 `DispatchReadyError` / `DispatchReadyRequiresLauncherError` / `ValueError`（環）時，MUST 將其收進 `errors`，並 MUST 仍繼續執行 `complete_tick`（派工側失敗不阻完成側）。

#### Scenario: fanout 拋例外仍跑 complete

- **WHEN** fanout 拋 `DispatchReadyRequiresLauncherError`，而有 in-flight job 可被完成側收斂
- **THEN** `errors` MUST 含該 fanout 失敗，且 `completed` MUST 仍反映完成側寫出的 manifest

