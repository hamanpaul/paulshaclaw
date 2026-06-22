## ADDED Requirements

### Requirement: persona catalog 全域 enforcement 旗標

`personas.yaml` SHALL 支援頂層 `enforcement` 旗標（值域 `shadow` | `enforce`），並提供 `loader.load_enforcement(path=None)` 讀取之。讀取 MUST fail-safe：缺檔、壞 YAML、缺 key 或非法值一律回傳 `shadow`，永不誤判為 `enforce`。新增此旗標 MUST NOT 改變既有 catalog 載入（`load_catalog` 僅讀 `roles`）。

#### Scenario: 預設 catalog 回傳 shadow

- **WHEN** 呼叫 `load_enforcement()`（讀預設 `personas.yaml`）
- **THEN** 回傳 `"shadow"`

#### Scenario: 顯式 enforce 被讀出

- **WHEN** `personas.yaml` 頂層為 `enforcement: enforce`
- **THEN** `load_enforcement` 回傳 `"enforce"`

#### Scenario: 缺 key / 非法值 / 缺檔 / 壞 YAML 一律退 shadow

- **WHEN** `enforcement` key 缺失、值非 `shadow`/`enforce`、檔案不存在，或 YAML 解析失敗
- **THEN** `load_enforcement` 回傳 `"shadow"`（fail-safe）

#### Scenario: 既有 catalog 載入不受影響

- **WHEN** `personas.yaml` 含新增的頂層 `enforcement` key
- **THEN** `load_catalog` 仍正常載入三角色 catalog，schema 驗證通過
