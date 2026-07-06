## ADDED Requirements

### Requirement: psc 傘狀命令入口
套件 SHALL 提供 console script `psc`：`psc memory …` 路由至 memory CLI、`psc coordinator …` 路由至 coordinator CLI，參數原樣透傳、零行為變更；未知或缺席子命令輸出 usage 並以 exit code 2 結束；既有 `python -m` 入口保留不變。

#### Scenario: 路由 memory 子命令
- **WHEN** 執行 `psc memory dream status`
- **THEN** 行為與 `python -m paulshaclaw.memory.cli memory dream status` 完全一致（含 exit code）

#### Scenario: 未知子命令
- **WHEN** 執行 `psc nosuch`
- **THEN** 輸出 usage 並回 exit code 2

### Requirement: 版號三方一致
`VERSION`、pyproject `project.version` 與最新版本 tag SHALL 以正規化 semver 比對相等（tag 去 `v` 前綴）；一致性由測試套件檢查。

#### Scenario: 版號漂移被測試攔截
- **WHEN** `VERSION` 與 pyproject version 不一致
- **THEN** 一致性測試失敗
