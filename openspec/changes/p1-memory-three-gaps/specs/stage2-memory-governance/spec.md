## ADDED Requirements

### Requirement: janitor 對 import ledger 壞行容錯
janitor 讀取 import ledger 供 reactivation 訊號時 SHALL 逐行解析：空行或無法解析之行 skip 並計數，其餘行照常處理；不得因單行損毀中止整段 reactivation 掃描。

#### Scenario: ledger 混入壞行
- **WHEN** import ledger 含（空行、壞 JSON、正常行）混排
- **THEN** 正常行全數處理，warning 報告 `skipped N bad line(s)`，reactivation 結果照常產出

#### Scenario: 壞行計數示警
- **WHEN** skip 計數大於 0
- **THEN** warning 含確切計數，供人工評估寫入端是否有系統性損壞
