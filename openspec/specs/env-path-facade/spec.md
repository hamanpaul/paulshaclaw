# env-path-facade Specification

## Purpose
TBD - created by archiving change p2-usability-phase0. Update Purpose after archive.
## Requirements
### Requirement: 路徑解析 facade
套件 SHALL 提供集中路徑 facade（`paulshaclaw/config/paths.py`）：`repo_root / memory_root / agents_root / config_root / worktree_root`，解析序為對應 `PSC_*` 環境變數優先、path-split 契約預設次之；facade 僅依賴 stdlib。

#### Scenario: env 覆寫生效
- **WHEN** 設定 `PSC_MEMORY_ROOT` 指向自訂路徑
- **THEN** 所有經 facade 取得 memory root 的模組使用該路徑

#### Scenario: 未設 env 走契約預設
- **WHEN** 相關 `PSC_*` 皆未設定
- **THEN** facade 回傳既有 path-split 契約預設值，行為與現行一致

### Requirement: facade 為唯一 home 推導點
`Path.home()` 直接呼叫 SHALL 僅存在於 facade 本體；`paulshaclaw/` 其餘模組（tests 除外）之直接呼叫點為零，路徑一律經 facade 取得。

#### Scenario: 假 HOME 全套件可運作
- **WHEN** 在假 `$HOME` 與自訂 `PSC_*` 環境下執行測試套件
- **THEN** 無任何模組繞過 facade 觸及真實使用者家目錄

