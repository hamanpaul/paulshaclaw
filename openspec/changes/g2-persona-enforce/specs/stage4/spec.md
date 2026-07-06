## ADDED Requirements

### Requirement: per-persona enforce 翻牌
persona scope 檢查 SHALL 支援 per-persona `enforcement` override（`roles.<name>.enforcement`，缺省繼承全域）；值為 `enforce` 的 persona 其 PR-bound manifest verdict 違規時 SHALL exit 非零；`shadow` persona 行為維持恆放行；未知值 SHALL 視為 shadow 並輸出 warning。

#### Scenario: builder enforce 違規被擋
- **WHEN** builder（enforcement: enforce）的 PR-bound manifest verdict 含越界 write_paths
- **THEN** scope_ci exit 1

#### Scenario: shadow persona 零回歸
- **WHEN** manager（繼承全域 shadow）的 manifest verdict 含越界
- **THEN** scope_ci exit 0（現行為不變）

### Requirement: manifest PR 綁定
scope_ci SHALL 以 head branch 與 slice_id 匹配取得 PR-bound manifest；無匹配或多筆匹配 SHALL 視同無 manifest；不得以 mtime 最新者替代。

#### Scenario: 無關 manifest 不得頂替
- **WHEN** handoff 目錄存在其他 slice 的較新 manifest 而 head branch 對應之 manifest 不存在
- **THEN** 視同無 manifest（進入 governed-paths 判定），不採用該無關 manifest

### Requirement: 無 manifest 的 governed-paths fail-closed
enforce 模式下無 PR-bound manifest 時，變更集與 enforce personas `write_paths` 聯集有交集者 SHALL exit 非零；豁免 SHALL 僅經顯式 `policy-exempt:persona-scope` label；無交集之 PR SHALL 不受影響（exit 0）。

#### Scenario: 省略 manifest 不再繞過
- **WHEN** PR 變更 builder 治理路徑內檔案且未附任何 manifest
- **THEN** scope_ci exit 1

#### Scenario: 無關 PR 不受影響
- **WHEN** PR 僅變更治理路徑外檔案且無 manifest
- **THEN** scope_ci exit 0
