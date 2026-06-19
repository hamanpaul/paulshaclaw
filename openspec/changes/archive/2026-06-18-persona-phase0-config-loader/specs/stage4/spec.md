## MODIFIED Requirements

### Requirement: Persona contract 三角色基線

Stage4 persona catalog MUST 定義 `manager`、`builder`、`reviewer` 三角色，且 MUST 由 `personas.yaml` 載入（config-driven，不得寫死於程式碼）。每個角色定義 MUST 至少包含 `role`、`version`、`summary`、`allowed_phases`、`write_paths`、`allowed_tools`，並 MUST 可通過 `validate_persona_schema`。三角色 `write_paths`／`allowed_tools` MUST 反映多 agent 派工流程：`manager` 可寫 `docs/**`／`openspec/**`／`lifecycle.yaml`／`runtime/handoff/**`；`builder` 可寫 `paulshaclaw/**`／`tests/**`／`openspec/changes/archive/**` 且 `allowed_tools` 不含 `git push`／`gh pr`；`reviewer` 僅可寫 `reports/review/**` 且不含改 code 工具。

#### Scenario: 三角色 contract 可通過 schema 驗證

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.PersonaSchemaTests -v`
- **THEN** 測試 MUST 驗證缺漏必要欄位會被拒絕，且三角色完整定義可通過

#### Scenario: catalog 由 personas.yaml 載入並符合 v2 scope

- **WHEN** 操作者載入 `paulshaclaw/persona/personas.yaml` 的 catalog
- **THEN** 載入結果 MUST 含三角色、通過 `validate_persona_schema`，且 `manager` 可寫 `openspec/**`、`builder` 可寫 `openspec/changes/archive/**` 並其工具不含 `git push`、`reviewer` 僅可寫 `reports/review/**`

## ADDED Requirements

### Requirement: Persona catalog 由 config 載入且 fail-closed

Stage4 SHALL 提供 catalog loader，從 `personas.yaml`（預設 `paulshaclaw/persona/personas.yaml`，可由路徑覆寫）載入三角色契約。當檔案缺失、解析失敗或 schema 驗證未過時，loader MUST fail-closed（raise 並帶可辨識原因），MUST NOT 回退到空或部分 catalog。

#### Scenario: 缺檔或非法 config 被 fail-closed 拒絕

- **WHEN** loader 載入不存在的路徑、或 schema 不合法的 `personas.yaml`
- **THEN** loader MUST raise 並帶可辨識原因，MUST NOT 回傳空／部分 catalog

#### Scenario: 合法 config round-trip

- **WHEN** loader 載入隨套件出貨的預設 `personas.yaml`
- **THEN** 回傳 `dict[str, PersonaContract]` MUST 含 `manager`／`builder`／`reviewer` 且通過 `validate_persona_schema`
