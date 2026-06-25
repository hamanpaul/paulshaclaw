# stage2-noise-governance

knowledge 噪音的判準（classifier）、產生端過濾、回溯 prune 與稽核 manifest。

## ADDED Requirements

### Requirement: 以 body 內容判定 noise

系統 SHALL 提供純函式 `classify_noise(frontmatter, body)`，回傳 `(is_noise, reason)`，且判定**僅依 body 內容**，不依賴 frontmatter 的 `atom_title` / `title` / `project`。判定規則依序為：(1) body strip 後第一行為 importer 結構 heading（`## CWD` / `## Source` / `## Prompts` / `## Touched files` / `## Referenced artifacts` / `## Summary`）→ `structural-echo`；(2) body strip 後 < 40 字 → `empty`；(3) body 含 `(無內容)` / `尚未收到您的具體需求` / `目前尚未收到`，或本體僅 `- (none)` / `(unknown)` → `placeholder`；皆不命中則非 noise。

#### Scenario: 結構段落 echo 判為 noise

- **WHEN** slice body 第一行為 `## CWD`、`## Prompts`、`## Source`、`## Touched files`、`## Referenced artifacts` 或 `## Summary`
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `structural-echo:<section>`

#### Scenario: 空殼與 placeholder 判為 noise

- **WHEN** slice body strip 後少於 40 字，或含 `(無內容)` / `尚未收到您的具體需求` / `目前尚未收到` 等 placeholder 字串
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `empty` 或 `placeholder`

#### Scenario: 有真內容者保留（精度防誤刪）

- **WHEN** slice 的 `atom_title` 為 `untitled` 或 `project` 為 username fallback，但 body 含足夠真實內容（例如 checklist、技術結論）
- **THEN** `classify_noise` SHALL 回 `is_noise=False`

### Requirement: 產生端過濾防止噪音新生

atomize 的 promote pass SHALL 在 slice 通過 frontmatter 驗證後、寫入 knowledge 前，對每個 slice 套用 `classify_noise`；判為 noise 者 MUST NOT 寫入 knowledge 層、MUST NOT 建立 semantic relation，並 SHALL 計入結果 summary 的 `noise_dropped`。source fragment 的 archive 與 session 的 promoted 標記 SHALL 不受影響。

#### Scenario: noise slice 被產生端丟棄

- **WHEN** promoter 對某 session 產出一個 body 為結構段落 echo 的 slice
- **THEN** 該 slice MUST NOT 出現在 knowledge 層，且 summary `noise_dropped` SHALL 反映被丟棄數，source fragment SHALL 仍被 archive

#### Scenario: 乾淨 slice 正常寫入

- **WHEN** promoter 產出 body 為真實萃取內容的 slice
- **THEN** 該 slice SHALL 正常寫入 knowledge 並建立其 relation

### Requirement: 回溯 prune 既有噪音

系統 SHALL 提供 `psc memory knowledge prune-noise` 子命令掃描 `knowledge/**.md`（排除 `*-moc.md`），對每檔以 `classify_noise` 判定。預設 `--dry-run` MUST NOT 修改任何檔，僅列出將刪清單與 reason 統計。`--apply` SHALL hard delete 命中檔並重建 MOC。命令 SHALL 一律輸出稽核 manifest 至 `runtime/ledger/prune-<now>.jsonl`（每行含 slice_id / project / path / reason）。

#### Scenario: dry-run 不動檔

- **WHEN** 執行 `prune-noise --dry-run`
- **THEN** 命令 SHALL 列出將刪 slice 與 reason 統計，且 knowledge 層任何檔 MUST NOT 被刪除或修改

#### Scenario: apply 刪噪音並保留乾淨 slice

- **WHEN** 執行 `prune-noise --apply`，knowledge 同時含噪音與乾淨 slice
- **THEN** 命中 noise 的檔 SHALL 被 hard delete、乾淨 slice SHALL 全數保留、manifest SHALL 記錄每筆刪除、MOC SHALL 重建且不含已刪 slice

#### Scenario: 單檔刪除失敗不中止整體

- **WHEN** `--apply` 過程中某檔刪除失敗
- **THEN** 該筆 SHALL 以 `status=error` 記入 manifest、命令 SHALL 跳過該檔並續處理其餘檔
