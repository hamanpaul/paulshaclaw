# deck-schema Specification

## Purpose
TBD - created by archiving change deck-cards-combo-phase-a. Update Purpose after archive.
## Requirements
### Requirement: Card schema 與 fail-closed 載入
deck SHALL 以 dataclass + validator 定義 Card（`id`、`kind`、`type`（interactive|headless）、`class`（core|niche|emergency）、`skill_ref`、`requires[]`、`produces[]`、`persona_binding`、`provider_binding`、可選 `slice_group`——連續同組 headless 卡編譯時合併為單一 slice，對應「一次 one-shot 派工涵蓋多個 phase」的現實），載入 `cards.yaml` 時 MUST fail-closed：任一卡片非法（缺必要欄位、枚舉值非法、YAML 壞損）即整批拒載並回報明確錯誤，不得部分載入。

#### Scenario: 合法卡片目錄載入成功
- **WHEN** `cards.yaml` 所有卡片欄位合法
- **THEN** 載入回傳完整卡片目錄，且每張卡的欄位型別與枚舉值已驗證

#### Scenario: 單張壞卡導致整批拒載
- **WHEN** `cards.yaml` 中任一張卡的 `type` 為未知枚舉值
- **THEN** 載入 raise 明確錯誤（含卡片 id 與欄位名），不回傳任何卡片

### Requirement: Combo schema 與環偵測
deck SHALL 定義 Combo（`id`、`task_type`、有序 `cards[]`（各項含 `ref` 與可選 `depends_on`）、`gate_spine[]`）。載入時 MUST 驗證：所有 `ref` 存在於卡片目錄、`depends_on` 無環、gate_spine 引用的卡片存在。

#### Scenario: 未知卡片引用被拒
- **WHEN** combo 的 `cards[].ref` 引用不存在的 card id
- **THEN** 載入 raise 明確錯誤並列出未知 ref

#### Scenario: depends_on 成環被拒
- **WHEN** combo 內卡片 `depends_on` 形成循環
- **THEN** 載入 raise 明確錯誤並列出環路徑

### Requirement: 佔位符白名單
卡片 `requires`/`produces` glob 中 SHALL 僅允許 `<task-slug>` 與 `<change>` 兩個佔位符；出現其他 `<...>` 形式 MUST 於載入時拒絕。

#### Scenario: 未知佔位符被拒
- **WHEN** 某卡 `produces` 含 `<feature-name>` 佔位符
- **THEN** 載入 raise 明確錯誤（含卡片 id 與非法佔位符名）

### Requirement: frontmatter 契約對齊測試
deck schema 測試 SHALL 斷言編譯輸出的 frontmatter 欄位集合恰為 `coordinator/autonomy.py::parse_spec_frontmatter` 接受的欄位（`dispatch`、`slice_id`、`plan`、`depends_on`），防止發明 runtime 會忽略的欄位。

#### Scenario: 欄位集合漂移被測試攔截
- **WHEN** 編譯器輸出新增了 runtime 契約以外的 frontmatter 欄位
- **THEN** 對齊測試失敗並指出多餘欄位

### Requirement: deck 包零 import 鐵律
`paulshaclaw/deck/**` SHALL NOT import `paulshaclaw.lifecycle` 或 `paulshaclaw.memory`（含 transitively 經 deck 自身模組）；MUST 以 import-lint 測試強制。

#### Scenario: 違規 import 被 lint 測試攔截
- **WHEN** deck 包任一模組出現 `paulshaclaw.lifecycle` 或 `paulshaclaw.memory` import
- **THEN** import-lint 測試失敗並列出違規檔案

