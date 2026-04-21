# stage4 Specification

## Purpose

Stage 4 SHALL 定義 persona contract / handoff / guardrail 的最小可驗收契約，並在 consume Stage3 phase/gate 輸出的前提下，提供可追溯的 shadow-run 驗證路徑。

## Requirements

### Requirement: Persona contract 三角色基線

Stage4 persona contract MUST 定義 `manager`、`builder`、`reviewer` 三角色。每個角色定義 MUST 至少包含 `role_id`、`allowed_phases`、`allowed_tools`、`allowed_paths`、`handoff_targets`。

#### Scenario: 三角色 contract 可通過 schema 驗證

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.PersonaSchemaTests -v`
- **THEN** 測試 MUST 驗證缺漏必要欄位會被拒絕，且三角色完整定義可通過

### Requirement: allowed_phases 對齊 Stage3 正規 phase

Stage4 的 `allowed_phases` MUST 僅使用 Stage3 canonical phase vocabulary（`research`、`define`、`plan`、`build`、`verify`、`review`、`ship`），且 Stage4 MUST NOT 重新定義 phase 名稱或 gate 狀態語義。

#### Scenario: allowed_phases 是 Stage3 phase 子集合

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.AllowedPhasesTests.test_allowed_phases_subset_of_stage3_vocabulary -v`
- **THEN** 測試 MUST 驗證各角色 phase 設定未超出 Stage3 正規集合

### Requirement: Handoff schema 與 Stage3 gate 輸出相容

Stage4 handoff message schema MUST 至少包含 `from_role`、`to_role`、`slice_id`、`phase`、`gate_status`、`artifact_refs`、`summary`、`created_at`。其中 `phase` 與 `gate_status` MUST 可直接由 Stage3 lifecycle/gate 輸出消費。

#### Scenario: handoff message 缺欄或非法 phase/gate 會被拒絕

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.HandoffSchemaTests -v`
- **THEN** 測試 MUST 驗證非法 handoff message 會失敗，合法 message 可供 coordinator route 使用

### Requirement: Guardrail 必須拒絕越界工具與路徑

Stage4 guardrail MUST 採 fail-closed：工具不在 `allowed_tools` 或路徑不在 `allowed_paths` 時必須拒絕，且拒絕結果 MUST 帶有可審計原因。

#### Scenario: 工具或路徑越界會被阻擋並可審計

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.GuardrailTests -v`
- **THEN** 測試 MUST 驗證越界請求被拒絕，並回傳可寫入 evidence 的拒絕理由

### Requirement: Stage4 只 consume Stage3，不反向修改 Stage3

Stage4 MUST 只消費 Stage3 既有 phase/gate 契約，不得在 Stage4 規格宣告 Stage3 lifecycle runtime 行為變更。任何 Stage3 phase 或 gate output 變更 MUST 先由 Stage3 change 更新 canonical spec，再由 Stage4 follow-up consume。

#### Scenario: Stage4 規格不宣告反向修改 Stage3

- **WHEN** 審查者檢視 `openspec/specs/stage3/spec.md` 與 `openspec/specs/stage4/spec.md`
- **THEN** Stage4 條款 MUST 只描述消費關係與相容性，不包含對 Stage3 runtime 的反向要求

### Requirement: Stage4 提供 shadow-run 驗證與證據歸檔

Stage4 SHALL 提供 shadow-run 驗證流程，並將 persona contract、handoff、guardrail 決策輸出歸檔於 Stage4 workstream evidence 路徑。

#### Scenario: shadow-run 驗證結果可追溯

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.ShadowRunTests -v`
- **THEN** 測試 MUST 驗證輸出可對應角色/phase/gate/guardrail 決策，並可保存到 `docs/superpowers/workstreams/stage4-persona-contract/evidence/`
