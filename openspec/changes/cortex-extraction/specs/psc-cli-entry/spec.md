## MODIFIED Requirements

### Requirement: psc 傘狀命令入口
套件 SHALL 提供 console script `psc`：`psc coordinator …` 以 thin shim lazy import `paulsha_cortex` 的 CLI 入口並原樣透傳參數（使用者面行為與拆分前一致）；`psc deck …` 路由至 `paulshaclaw.deck.cli`；`psc memory …` 維持 tombstone（輸出遷移指引，exit code 2）。cortex 未安裝時 `psc coordinator` MUST 輸出明確安裝指引（仿 memory tombstone 文案格式）並以 exit code 2 結束；未知或缺席子命令輸出 usage 並以 exit code 2 結束；既有 `python -m` 入口保留不變。

#### Scenario: 路由 coordinator 子命令（shim 透傳）
- **WHEN** 已安裝 paulsha-cortex 且執行 `psc coordinator status`
- **THEN** 行為與直接呼叫 cortex CLI 的對應子命令完全一致（含 exit code）

#### Scenario: cortex 未安裝
- **WHEN** 環境未安裝 paulsha-cortex 且執行 `psc coordinator status`
- **THEN** 輸出含安裝指引的錯誤訊息並回 exit code 2

#### Scenario: 未知子命令
- **WHEN** 執行 `psc nosuch`
- **THEN** 輸出 usage 並回 exit code 2
