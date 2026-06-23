## ADDED Requirements

### Requirement: run_tick 跑 fanout→complete 一趟且 idle-gated

`coordinator-tick` SHALL 提供 `manager.run_tick(dispatcher, *, metas, launcher, persona="builder", is_satisfied, gate_runner=None, handoff_dir=autonomy.DEFAULT_HANDOFF_DIR, require_idle=False, max_load=1.0, idle_probe=os.getloadavg, clock=_utcnow)`。當 `require_idle` 為真且 `memory.dream.idle.is_idle(max_load, idle_probe)` 為假時，MUST 直接回 `{"skipped": "not-idle", "dispatched": [], "completed": [], "errors": []}` 且不派工、不輪詢。否則 MUST 先跑 fanout（`autonomy.dispatch_ready`）再跑 `complete_tick`，回 `{"skipped": False, "dispatched": [...], "completed": [...], "errors": [...]}`。

#### Scenario: idle 未達整趟跳過

- **WHEN** `require_idle=True` 且注入的 `idle_probe` 回報高 load（超過 `max_load`）
- **THEN** `run_tick` MUST 回 `skipped=='not-idle'`、`dispatched`/`completed` 為空，且 MUST NOT 呼叫 dispatch 或寫任何 manifest

#### Scenario: idle 達標跑完整 tick

- **WHEN** `require_idle=True` 且 `idle_probe` 回報低 load
- **THEN** `run_tick` MUST 跑 fanout 再跑 complete，回 `skipped==False` 且 `completed` 反映完成側結果

### Requirement: fanout 失敗不連累 complete

`run_tick` 內 fanout 拋出 `DispatchReadyError` 或 `DispatchReadyRequiresLauncherError` 時，MUST 將其收進回傳的 `errors`，並 MUST 仍繼續執行 `complete_tick`（派工側失敗不阻完成側）。

#### Scenario: fanout 拋例外仍跑 complete

- **WHEN** 注入的 dispatch 路徑對 fanout 拋 `DispatchReadyRequiresLauncherError`，而有 in-flight job 可被完成側收斂
- **THEN** `run_tick` 回的 `errors` MUST 含該 fanout 失敗，且 `completed` MUST 仍反映完成側寫出的 manifest
