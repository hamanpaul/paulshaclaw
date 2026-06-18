# stage4 Specification

## Purpose

Stage 4 SHALL 定義 persona contract / handoff / guardrail 的最小可驗收契約，並在 consume Stage3 phase/gate 輸出的前提下，提供可追溯的 shadow-run 驗證路徑。
## Requirements
### Requirement: Persona contract 三角色基線

Stage4 persona catalog MUST 定義 `manager`、`builder`、`reviewer` 三角色，且 MUST 由 `personas.yaml` 載入（config-driven，不得寫死於程式碼）。每個角色定義 MUST 至少包含 `role`、`version`、`summary`、`allowed_phases`、`write_paths`、`allowed_tools`，並 MUST 可通過 `validate_persona_schema`。三角色 `write_paths`／`allowed_tools` MUST 反映多 agent 派工流程：`manager` 可寫 `docs/**`／`openspec/**`／`lifecycle.yaml`／`runtime/handoff/**`；`builder` 可寫 `paulshaclaw/**`／`tests/**`／`openspec/changes/archive/**` 且 `allowed_tools` 不含 `git push`／`gh pr`；`reviewer` 僅可寫 `reports/review/**` 且不含改 code 工具。

#### Scenario: 三角色 contract 可通過 schema 驗證

- **WHEN** 操作者執行 `python -m unittest tests.test_stage4_persona_contract.PersonaSchemaTests -v`
- **THEN** 測試 MUST 驗證缺漏必要欄位會被拒絕，且三角色完整定義可通過

#### Scenario: catalog 由 personas.yaml 載入並符合 v2 scope

- **WHEN** 操作者載入 `paulshaclaw/persona/personas.yaml` 的 catalog
- **THEN** 載入結果 MUST 含三角色、通過 `validate_persona_schema`，且 `manager` 可寫 `openspec/**`、`builder` 可寫 `openspec/changes/archive/**` 並其工具不含 `git push`、`reviewer` 僅可寫 `reports/review/**`

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

### Requirement: Persona catalog 由 config 載入且 fail-closed

Stage4 SHALL 提供 catalog loader，從 `personas.yaml`（預設 `paulshaclaw/persona/personas.yaml`，可由路徑覆寫）載入三角色契約。當檔案缺失、解析失敗或 schema 驗證未過時，loader MUST fail-closed（raise 並帶可辨識原因），MUST NOT 回退到空或部分 catalog。

#### Scenario: 缺檔或非法 config 被 fail-closed 拒絕

- **WHEN** loader 載入不存在的路徑、或 schema 不合法的 `personas.yaml`
- **THEN** loader MUST raise 並帶可辨識原因，MUST NOT 回傳空／部分 catalog

#### Scenario: 合法 config round-trip

- **WHEN** loader 載入隨套件出貨的預設 `personas.yaml`
- **THEN** 回傳 `dict[str, PersonaContract]` MUST 含 `manager`／`builder`／`reviewer` 且通過 `validate_persona_schema`

### Requirement: Handoff manifest 讀寫且 read fail-closed

Stage4 SHALL 提供 handoff manifest 的持久化讀寫，落地於 `runtime/handoff/<slice_id>.json`（schema 沿用既有 handoff message：`from_role`、`to_role`、`phase`、`gate_status`、`slice_id`、`summary`、`artifact_refs`、`created_at`，並得帶 `base`、`head`）。`write_manifest(path, payload)` MUST 序列化 payload 並確保父目錄存在。`read_manifest(path)` MUST 經 `contract.validate_handoff_message` 驗證；當 manifest 非法時 MUST raise（fail-closed），當檔案缺失時 MUST raise（fail-closed），MUST NOT 回傳空或部分 manifest。

#### Scenario: 合法 manifest round-trip

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.HandoffManifestTests.test_round_trip -v`
- **THEN** 測試 MUST 驗證 `write_manifest` 寫出的合法 manifest 可被 `read_manifest` 讀回且欄位一致

#### Scenario: 非法或缺檔 manifest 被 fail-closed 拒絕

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.HandoffManifestTests -v`
- **THEN** 測試 MUST 驗證 `read_manifest` 對非法 manifest 與缺檔皆 raise，MUST NOT 回傳空／部分結果

### Requirement: Persona contract render 為 prompt 前言

Stage4 SHALL 提供 `render_contract_prompt(role, catalog=None, overlay=None) -> str`，reuse `context.build_persona_context` 算出角色契約，輸出**確定性**的 prompt 前言字串，內容 MUST 至少陳述角色名稱、`allowed_phases`、`write_paths` 與 `effective_tools`（即派工強制點 ① 的 contract 注入）。當 role 未知時 MUST raise `ValueError`。

#### Scenario: render 輸出含角色 scope

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.RenderContractPromptTests.test_contains_role_scope -v`
- **THEN** 測試 MUST 驗證輸出字串含角色名稱與該角色各 `write_paths` 子字串

#### Scenario: 未知 role 被拒絕

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.RenderContractPromptTests.test_unknown_role_raises -v`
- **THEN** 測試 MUST 驗證未知 role 會 raise `ValueError`

### Requirement: Shadow diff-gate CLI 恆放行可翻 enforce

Stage4 SHALL 提供薄 CLI `python -m paulshaclaw.persona.gate --role R --base B --head H --manifest PATH [--enforce]`，以 `git diff --name-only <base>...<head>` 取得變更檔，逐檔以 `guardrail.evaluate_filesystem(role, path)` 評估，並讀驗 handoff manifest，輸出 JSON verdict `{role, changed_paths, violations, handoff_ok, ok}`。catalog MUST 由 `loader.load_catalog()` 取得。**預設 shadow 模式 MUST 恆 exit 0（僅觀測/記錄）**；帶 `--enforce` 時當 `ok` 為 false MUST exit 1、`ok` 為 true MUST exit 0。判定邏輯 MUST 放於可測試函式，`main(argv)` 為薄殼。

#### Scenario: in-scope diff verdict ok

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.GateVerdictTests.test_in_scope_ok -v`
- **THEN** 測試 MUST 驗證對符合角色 write scope 的變更檔，verdict 的 `violations` 為空且 `ok` 為 true

#### Scenario: out-of-scope diff 產生 violation

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.GateVerdictTests.test_out_of_scope_violation -v`
- **THEN** 測試 MUST 驗證對越界變更檔，verdict 的 `violations` 含該 path 與拒絕原因且 `ok` 為 false

#### Scenario: shadow 恆 exit 0 而 enforce 違規 exit 1

- **WHEN** 操作者執行 `python -m unittest tests.test_persona_phase1_shadow_gate.GateExitCodeTests -v`
- **THEN** 測試 MUST 驗證越界 diff 在預設 shadow 模式 `main` 回傳 0，帶 `--enforce` 時回傳 1；in-scope diff 兩模式皆回傳 0

