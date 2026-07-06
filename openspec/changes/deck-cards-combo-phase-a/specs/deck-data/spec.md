# deck-data

## ADDED Requirements

### Requirement: feature-oneshot combo 轉錄
deck SHALL 內建自 `feature-delivery-pipeline` SKILL.md 轉錄的卡片與 `feature-oneshot` combo：11 個 phase 全數對應到卡片（interactive/headless 正確分型），每張卡 `produces` 僅含可機械驗證的 artifact glob，`gate_spine` 對應該 SKILL.md 的 phase gate。轉錄後 MUST 通過 deck-schema 全部載入驗證。

#### Scenario: 轉錄資料通過驗證
- **WHEN** 載入 `cards.yaml` 與 `combos/feature-oneshot.yaml`
- **THEN** 驗證通過，11 個 phase 各有對應卡片

#### Scenario: 實戰編譯通過整合驗收
- **WHEN** 以 feature-oneshot 編譯樣例 task
- **THEN** 通過 deck-compile 的 parse-level 整合驗收（scan/cycles/ready-empty）

### Requirement: mcu-feature combo 轉錄（schema 泛化性驗證）
deck SHALL 內建自 `mcu-coding-skill` 轉錄的 `mcu-feature` combo（含 MCU 特有卡片增補）。此轉錄兼任 schema 泛化性壓力測試：若轉錄需要 schema 未支援的表達，MUST 回饋 schema 修訂而非硬塞。

#### Scenario: 第二 combo 通過同一驗證鏈
- **WHEN** 載入並編譯 mcu-feature 樣例 task
- **THEN** 通過與 feature-oneshot 相同的載入驗證與整合驗收
