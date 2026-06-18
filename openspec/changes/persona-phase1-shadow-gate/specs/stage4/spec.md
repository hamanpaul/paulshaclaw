## ADDED Requirements

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
