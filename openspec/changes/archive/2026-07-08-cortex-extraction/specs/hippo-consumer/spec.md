## MODIFIED Requirements

### Requirement: 允許 import 面限定
主 repo runtime 程式碼 MUST NOT import `paulsha_hippo`（原 `persona.contract`、`coordinator.manager` 兩處 `paulsha_hippo.lib.*` import 已隨治理包遷入 paulsha-cortex 並就地剪線）；`core/daemon.py` MUST NOT import hippo internals（含 `paulsha_hippo.atomizer.config`），`/agent` 命令 argv MUST 來自 daemon 自有 config。測試面例外：主 repo 測試套件 MAY import `paulsha_hippo.lib.lifecycle.schema`，僅限跨包對齊測試（PHASES 相等性）使用。

#### Scenario: import 面 CI 檢查
- **WHEN** CI 掃描主 repo 非測試程式碼對 `paulsha_hippo` 的 import
- **THEN** 出現任何 import MUST 使檢查失敗；`tests/` 內超出對齊測試用途的 import MUST 使檢查失敗

#### Scenario: daemon 不依賴 hippo 內部
- **WHEN** 安裝 paulsha-hippo 為套件且主 repo 移除 `paulshaclaw.memory` 後執行 `/agent start` 與 `/agent status`
- **THEN** 兩命令 MUST 正常運作（argv 來自 daemon config，不經 hippo 套件內相對路徑解析）
