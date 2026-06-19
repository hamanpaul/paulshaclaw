## ADDED Requirements

### Requirement: Stage 3 artifact schema 與 lifecycle template MVP

Stage 3 lifecycle MVP SHALL 提供可靜態驗證的 artifact frontmatter schema，且所有 lifecycle-managed artifact MUST 包含至少 `phase`、`project`、`slice_id`、`artifact_kind`、`version`、`created_at`、`created_by`、`source_session`、`gate_required`、`checksum`。  
Stage 3 同時 MUST 提供 `lifecycle.yaml` template，至少含 `project`、`current_slice`、`current_phase`、`workflow_version`、`last_ship`、`open_rework`、`open_rewind`、`stale_spikes`、`gates`。

#### Scenario: Frontmatter schema 測試可偵測缺欄與 checksum 錯誤

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.FrontmatterSchemaTests -v`
- **THEN** 測試 MUST 驗證缺欄位、非法 phase、錯誤 checksum 皆會被 static gate 拒絕，且有效 artifact 可通過

#### Scenario: lifecycle template 產出固定最小 shape

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.LifecycleTemplateTests -v`
- **THEN** 產生的 state MUST 含七個正規 phase gate key，且每個 gate 的 `last_check` / `status` 初值皆為 `null`

### Requirement: Stage 3 static gate 與最小事件流

Stage 3 lifecycle runtime SHALL 以 artifact-first/event-first 方式處理 phase 狀態。每個 phase 至少 MUST 支援 `phase.requested`、`phase.artifact_submitted`、`phase.gate_passed` 與 `phase.gate_failed` 事件。  
若收到 `phase.gate_failed`，replay 後狀態 MUST 轉為 `blocked:<phase>`；若收到 `phase.gate_passed`，該 phase 狀態 MUST 為 `passed`。

#### Scenario: gate passed 事件可回放成 passed 狀態

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.EventReplayTests.test_event_stream_rebuilds_current_phase_state -v`
- **THEN** 回放後 `current_phase` MUST 等於該 phase，且 `phase_status[phase]` MUST 等於 `passed`

#### Scenario: gate failed 事件會阻塞目前 phase

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.EventReplayTests.test_gate_failed_event_blocks_phase -v`
- **THEN** 回放後 `current_phase` MUST 為 `blocked:verify`（或對應失敗 phase），且 `blocked_phase` MUST 被設定

### Requirement: Golden slice 回歸必須覆蓋七階段

Stage 3 SHALL 提供 golden slice 測試，依序覆蓋 `/research → /define → /plan → /build → /verify → /review → /ship`。  
每個 phase 皆需通過 static gate 並寫入三個主事件（requested/submitted/passed）；最終 replay 結果 MUST 落在 `ship` 且無 blocked phase。

#### Scenario: Golden slice 全流程可通過

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.GoldenSliceTests -v`
- **THEN** 測試 MUST 驗證七階段均為 `passed`，且最終狀態 `current_phase` MUST 為 `ship`

### Requirement: Stage 1 / Stage 2 介面契約邊界

Stage 3 lifecycle MVP MUST 維持與 Stage 1/2 的最小耦合：
- 對 Stage 1：只依賴 daemon `/status`、`/dispatch <task-id>` 與 coordinator `create_job(*, phase, scope, payload)` seam，不得要求 Stage 1 變更啟動流程。
- 對 Stage 2：只交付 artifact pointer/copy 到 `inbox` 路由與 runtime lifecycle 事件/報告，不得由 Stage 3 直接寫入 `knowledge/*` 或直接控制 janitor `decayed/reactivation`。

#### Scenario: Stage 1 邊界有明確契約來源

- **WHEN** 審查者檢視 `openspec/specs/stage1-core-runtime/spec.md` 與 `openspec/specs/stage3/README.md`
- **THEN** Stage 3 依賴面 MUST 只包含 `/status`、`/dispatch` 與 coordinator seam，且不要求額外 Stage 1 命令

#### Scenario: Stage 2 邊界有明確契約來源

- **WHEN** 審查者檢視 `openspec/specs/stage2-memory-governance/spec.md` 與本變更的 Stage 3 requirement
- **THEN** Stage 3 產出路徑 MUST 符合 `inbox -> work-centric -> knowledge` 邊界，且 MUST NOT 宣告直接寫 `knowledge/*`
