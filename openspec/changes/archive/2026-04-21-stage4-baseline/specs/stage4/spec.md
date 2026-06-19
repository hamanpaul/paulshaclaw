## ADDED Requirements

### Requirement: Stage4 persona contract 最小角色集合

Stage4 persona contract SHALL 提供可驗證的 schema，且最小角色集合 MUST 包含 `manager`、`builder`、`reviewer`。每個角色定義 MUST 至少包含 `role_id`、`allowed_phases`、`allowed_tools`、`allowed_paths`、`handoff_targets`。

#### Scenario: persona schema 可驗證必要欄位

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.PersonaSchemaTests -v`
- **THEN** 測試 MUST 驗證缺少必要欄位會被拒絕，且三角色完整定義可通過

#### Scenario: 最小角色集合存在且不可缺漏

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.RoleBaselineTests.test_required_roles_present -v`
- **THEN** 測試 MUST 驗證 `manager`、`builder`、`reviewer` 三角色皆存在，且 `handoff_targets` 非空

### Requirement: Stage4 allowed_phases 僅 consume Stage3 正規 phase

Stage4 persona 的 `allowed_phases` MUST 僅使用 Stage3 canonical phase vocabulary（`research`、`define`、`plan`、`build`、`verify`、`review`、`ship`）。Stage4 MUST NOT 新增 phase alias、改名 phase 或覆寫 Stage3 gate 狀態語義。

#### Scenario: allowed_phases 為 Stage3 phase 子集合

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.AllowedPhasesTests.test_allowed_phases_subset_of_stage3_vocabulary -v`
- **THEN** 測試 MUST 驗證任一角色 `allowed_phases` 都是 Stage3 正規 phase 的子集合

#### Scenario: Stage4 不反向定義 Stage3 phase

- **WHEN** 操作者執行 `rg -n "alias|rename|override" openspec/specs/stage4/spec.md`
- **THEN** 審查結果 MUST 不出現宣告 Stage4 覆寫 Stage3 phase/gate 語義的條款

### Requirement: Stage4 handoff message schema 可供 coordinator route 消費

Stage4 SHALL 定義 handoff message 最小 schema，MUST 至少包含 `from_role`、`to_role`、`slice_id`、`phase`、`gate_status`、`artifact_refs`、`summary`、`created_at`。handoff message 的 `phase` 與 `gate_status` MUST 可直接對應 Stage3 輸出。

#### Scenario: handoff schema 通過欄位驗證

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.HandoffSchemaTests -v`
- **THEN** 測試 MUST 驗證缺少必要欄位或非法 `phase`/`gate_status` 的 message 會被拒絕

#### Scenario: handoff phase/gate 與 Stage3 輸出相容

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.HandoffSchemaTests.test_stage3_phase_gate_compatibility -v`
- **THEN** 測試 MUST 驗證 handoff message 可直接使用 Stage3 的 phase 名稱與 gate 狀態值

### Requirement: Stage4 guardrail 必須拒絕越界工具與路徑

Stage4 guardrail MUST 對角色執行 fail-closed 檢查：
- 若請求工具不在角色 `allowed_tools`，MUST 拒絕。
- 若請求路徑不在角色 `allowed_paths`，MUST 拒絕。
- 拒絕結果 MUST 包含可審計拒絕原因與違規條件。

#### Scenario: 工具越界會被拒絕並記錄原因

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.GuardrailTests.test_disallow_tool_outside_allowlist -v`
- **THEN** 測試 MUST 驗證越界工具請求被拒絕，且回傳內含拒絕理由與角色識別

#### Scenario: 路徑越界會被拒絕並記錄原因

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.GuardrailTests.test_disallow_path_outside_scope -v`
- **THEN** 測試 MUST 驗證越界路徑請求被拒絕，且拒絕資訊可寫入審計證據

### Requirement: Stage4 MUST 提供 shadow-run 驗證流程

Stage4 SHALL 定義 shadow-run 驗證流程，用於不改動 Stage3 lifecycle/runtime 前提下，驗證 persona contract、handoff 與 guardrail 的行為一致性。shadow-run 產出 MUST 可歸檔到 Stage4 workstream evidence 目錄。

#### Scenario: shadow-run 可產出 persona/gate 驗證證據

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.ShadowRunTests -v`
- **THEN** 測試 MUST 驗證 shadow-run 可產生包含 role、phase、gate、guardrail decision 的驗證輸出

#### Scenario: Stage4 evidence 路徑可對應 workstream

- **WHEN** 操作者執行 `rg -n "docs/superpowers/workstreams/stage4-persona-contract/evidence" openspec/changes/stage4-persona-contract/tasks.md`
- **THEN** `tasks.md` MUST 定義可追溯 evidence 路徑，供 shadow-run 與拒絕案例保存
