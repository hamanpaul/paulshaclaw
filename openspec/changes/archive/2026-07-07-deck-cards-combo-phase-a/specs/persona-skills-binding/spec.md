# persona-skills-binding

## ADDED Requirements

### Requirement: personas.yaml skills 欄位載入與保留
`personas.yaml` 各 role SHALL 可宣告 `skills:`（card id 清單）；`persona/loader.py` MUST 讀取並保留該欄位至 `PersonaContract`（現行 loader 會丟棄未知欄位，需擴充），validator 對缺省該欄位的 role 維持相容（欄位可選；顯式 `skills: null` 等同未宣告——YAML 空值容錯，對抗審查裁決）。

#### Scenario: skills 欄位存續到 contract
- **WHEN** 某 role 宣告 `skills: [writing-plans, code-review]`
- **THEN** 載入後該 role 的 `PersonaContract` 暴露同一清單

#### Scenario: 未宣告 skills 的 role 不受影響
- **WHEN** 某 role 無 `skills:` 欄位
- **THEN** 載入成功，contract 的 skills 為空清單

### Requirement: card 引用 shadow 驗證
載入時 SHALL 驗證 `skills:` 引用的 card id 存在於 deck 卡片目錄；缺失 MUST 僅產生 warning（shadow，與全域 `enforcement: shadow` 一致），不得使載入失敗、不得改變 guardrail 行為。

#### Scenario: 未知 card id 僅告警
- **WHEN** 某 role `skills:` 引用不存在的 card id
- **THEN** 載入成功並輸出含 role 與缺失 id 的 warning
