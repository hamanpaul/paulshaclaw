## RENAMED Requirements

- FROM: `### Requirement: Alert-first multi-account presentation`
- TO: `### Requirement: Compact primary-account presentation`

## MODIFIED Requirements

### Requirement: Tmux footer status command

Stage 8 SHALL provide a tmux footer status command invocable as `python -m paulshaclaw.cost.status`. The command MUST print one line suitable for tmux `status-right`, MUST exit 0 for normal degraded display cases, and MUST preserve tmux responsiveness by reading cache before attempting provider refresh.

#### Scenario: Footer renders the balanced format

- **WHEN** the snapshot contains Codex 5h usage `18` with reset display `15:21`, weekly usage `41` with reset display `3d`, Claude unknown data, and two Copilot accounts `haman=724` and `arc=127`
- **THEN** the footer MUST include `cdx 5h:18%(15:21) wk:41%(3d)`
- **THEN** the footer MUST include `cc 5h:-- wk:--`
- **THEN** the footer MUST include `cpt 724` without account labels

#### Scenario: Stale provider is marked

- **WHEN** a provider is rendered from stale cache
- **THEN** the footer MUST append `~` to that provider abbreviation, such as `cdx~`

### Requirement: Compact primary-account presentation

footer 與 cockpit SHALL 僅顯示設定中第一個 enabled Copilot 帳號的已用用量，不顯示帳號名、id、類型或逐帳號明細。第一個 enabled 的順序 SHALL 由設定決定，不以帳號名稱寫死，不依次帳號告警、工作目錄或最近使用切換。其他啟用帳號 SHALL 繼續收集並保留在 snapshot JSON。

主帳號缺資料 SHALL 顯示 `--`，不得以 0 或其他帳號用量代替；主帳號 stale SHALL 保留 `cpt~` 標記及既有 stale 樣式。次帳號狀態 MUST NOT 影響摘要選擇或標記。讀取 cache SHALL 保持唯讀，不發出網路請求。

逐帳號 source_status 與 cache roundtrip SHALL 繼續保存；部分失敗 SHALL 只按同一 account id 回填舊值並標 stale，成功帳號保持 fresh，停用或刪除帳號不得復活。設定重排 SHALL 決定新的主帳號。AGY 的既有單一 active account 行為不變。

#### Scenario: Secondary unknown does not replace primary

- **WHEN** the first enabled account is 87% and a secondary account is unknown
- **THEN** the footer SHALL render `cpt 87%` and cockpit SHALL render `cpt: 87%`
- **THEN** no account labels or account detail rows SHALL appear in the cockpit banner

#### Scenario: Secondary critical does not replace primary

- **WHEN** the first enabled account is 20% and the secondary is 99%
- **THEN** the footer SHALL render `cpt 20%`

#### Scenario: Primary unavailable does not borrow secondary

- **WHEN** the first enabled account has no usable value and the secondary is 99%
- **THEN** the footer SHALL render `cpt --` and cockpit SHALL render `cpt: --`

#### Scenario: Primary stale remains explicit

- **WHEN** the first enabled account retains its previous 80% as stale
- **THEN** the footer SHALL render `cpt~ 80%` and cockpit SHALL render `cpt~: 80%`
