# stage3 Specification

## Purpose

Stage 3 SHALL 定義 artifact-first lifecycle MVP 的最小可驗收契約，涵蓋 frontmatter schema、`lifecycle.yaml` template、static gate、最小事件流與 golden slice 回歸，同時明確 Stage 1 dispatch seam 與 Stage 2 memory routing seam 的邊界。

## Requirements

### Requirement: Artifact frontmatter 與 lifecycle template 基線

Stage 3 lifecycle-managed artifact MUST 支援可靜態驗證的 frontmatter 欄位，至少包含：`phase`、`project`、`slice_id`、`artifact_kind`、`version`、`created_at`、`created_by`、`source_session`、`gate_required`、`checksum`。  
Stage 3 同時 MUST 提供 `lifecycle.yaml` 的最小 shape：`project`、`current_slice`、`current_phase`、`workflow_version`、`last_ship`、`open_rework`、`open_rewind`、`stale_spikes`、`gates`。

#### Scenario: Frontmatter schema 測試可驗證必要欄位與 checksum

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.FrontmatterSchemaTests -v`
- **THEN** 測試 MUST 驗證遺漏必要欄位、非法 phase 與錯誤 checksum 會被拒絕，且合法 artifact 可通過 static gate

#### Scenario: Lifecycle template 輸出固定欄位

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.LifecycleTemplateTests -v`
- **THEN** template 輸出 MUST 含七個 phase gate key，且每個 gate 的 `last_check` 與 `status` 初始值 MUST 為 `null`

### Requirement: Static gate 與事件回放狀態

Stage 3 lifecycle runtime SHALL 以事件流維護 phase 狀態，且至少 MUST 支援 `phase.requested`、`phase.artifact_submitted`、`phase.gate_passed`、`phase.gate_failed`。  
回放事件時，`phase.gate_passed` MUST 導致該 phase 狀態為 `passed`；`phase.gate_failed` MUST 導致狀態為 `blocked:<phase>`。

#### Scenario: gate passed 事件回放為 passed

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.EventReplayTests.test_event_stream_rebuilds_current_phase_state -v`
- **THEN** 回放後 `current_phase` MUST 等於被驗證 phase，且 `phase_status[phase]` MUST 等於 `passed`

#### Scenario: gate failed 事件回放為 blocked

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.EventReplayTests.test_gate_failed_event_blocks_phase -v`
- **THEN** 回放後 `current_phase` MUST 為 `blocked:verify`（或對應失敗 phase），且 `blocked_phase` MUST 被設定

### Requirement: Golden slice 七階段回歸

Stage 3 SHALL 提供 golden slice 測試，必須依序覆蓋 `/research -> /define -> /plan -> /build -> /verify -> /review -> /ship`。  
每個 phase artifact MUST 通過 static gate，並寫入 requested/submitted/passed 三類事件；最終回放狀態 MUST 收斂到 `ship` 且 `blocked_phase` 為空。

#### Scenario: Golden slice 全流程通過

- **WHEN** 操作者執行 `python -m unittest tests.test_stage3_lifecycle_mvp.GoldenSliceTests -v`
- **THEN** 測試 MUST 驗證七階段 `phase_status` 全為 `passed`，且最終 `current_phase` MUST 為 `ship`

### Requirement: Stage 1 / Stage 2 介面契約邊界

Stage 3 MUST 維持以下跨 stage 邊界：
- 對 Stage 1：只依賴 daemon `/status`、`/dispatch <task-id>` 與 coordinator `create_job(*, phase, scope, payload)` seam，不得要求 Stage 1 新增啟動流程耦合。
- 對 Stage 2：只透過 `inbox -> work-centric -> knowledge` 的既有治理路徑交付 artifact pointer/copy 與 lifecycle 事件，不得由 Stage 3 直接寫入 `knowledge/*` 或直接操作 janitor `decayed/reactivation` 流程。

#### Scenario: Stage 1 邊界符合 core-runtime 契約

- **WHEN** 審查者對照 `openspec/specs/stage1-core-runtime/spec.md` 與本規格
- **THEN** Stage 3 依賴面 MUST 僅限 `/status`、`/dispatch` 與 coordinator seam

#### Scenario: Stage 2 邊界符合 memory-governance 契約

- **WHEN** 審查者對照 `openspec/specs/stage2-memory-governance/spec.md` 與本規格
- **THEN** Stage 3 流程 MUST 不宣告直接寫 `knowledge/*`，且 MUST 維持 `inbox -> work-centric -> knowledge` 路徑約束
