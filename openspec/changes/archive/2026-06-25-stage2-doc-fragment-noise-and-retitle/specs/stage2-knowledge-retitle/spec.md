# stage2-knowledge-retitle

untitled 真知識 slice 的標題重生（gemma4 body 蒸餾）、檔名重命名（保留 slice_id）與稽核 manifest；`slugify` 保留 CJK。

## ADDED Requirements

### Requirement: slugify 保留 CJK 文字

`slugify(title)` SHALL 保留 Unicode 文字字元（含 CJK）與數字，僅將標點、空白與符號折成 `-`，使純 CJK 標題產生非空、可讀的 slug；title 去除非文字字元後為空時，SHALL fallback 為 `untitled`。此變更 MUST NOT 改變既有 ASCII 標題的 slug 結果。

#### Scenario: 純 CJK 標題產生 CJK slug

- **WHEN** `slugify("動工前")`
- **THEN** 回傳值 SHALL 為非空且保留 CJK（非 `untitled`）

#### Scenario: ASCII 標題 slug 不變

- **WHEN** `slugify("CI gating note")`
- **THEN** 回傳值 SHALL 為 `ci-gating-note`（與既有行為一致）

#### Scenario: 空/純標點標題仍 fallback

- **WHEN** `slugify("---")` 或 `slugify("")`
- **THEN** 回傳值 SHALL 為 `untitled`

### Requirement: untitled 真知識 slice 標題重生與重命名

系統 SHALL 提供 `psc memory knowledge retitle-untitled` 子命令，掃描 `knowledge/**.md`（排除 `*-moc.md`、限 `memory_layer: knowledge`），對 `title` 為 `untitled`（或檔名為 `untitled--`）且**非 doc-fragment**（以 `classify_noise` + 語料雙重防護排除）的 slice，用注入式 runner（預設 gemma4）對 body 蒸餾出 ≤20 字 zh-TW 標題，stamp `title` / `atom_title` / `aliases`，並**重命名檔案為 `<new-slug>--<slice_id>.md`（保留 slice_id 與 body 不變）**。預設 `--dry-run` MUST NOT 修改任何檔；`--apply` SHALL 套用變更並重建 MOC。命令 SHALL 一律輸出稽核 manifest 至 `runtime/ledger/retitle-<now>.jsonl`。gemma4（runner）離線或標題重生失敗的 slice SHALL 被 skip 並於 manifest 記 `status`，命令 MUST NOT 因此失敗。

#### Scenario: dry-run 不動檔

- **WHEN** 執行 `retitle-untitled --dry-run`
- **THEN** 命令 SHALL 列出將重命名/stamp 的 slice 與新標題，且 knowledge 任何檔 MUST NOT 被修改或重命名

#### Scenario: apply 重生標題並改名保留 slice_id

- **WHEN** 對某 `untitled--<sid>.md` 真知識 slice 執行 `retitle-untitled --apply`，runner 回傳有效標題
- **THEN** 該檔 SHALL 被重命名為 `<new-slug>--<sid>.md`（`slice_id` 不變、body 不變）、frontmatter `title`/`atom_title` SHALL 更新為新標題、manifest SHALL 記錄該筆、MOC SHALL 重建且 raw brief 不再含該 `untitled--` target

#### Scenario: doc-fragment 不被 retitle

- **WHEN** 某 `untitled--` slice 的 body 為 instruction 文件碎片（doc-fragment）
- **THEN** retitle SHALL 跳過該 slice（交由 prune 處理），MUST NOT 為其重生標題

#### Scenario: runner 離線時 skip 不失敗

- **WHEN** 執行 `retitle-untitled --apply` 但 runner（gemma4）離線或無法產生標題
- **THEN** 對應 slice SHALL 被 skip 並於 manifest 記其 status、原檔 SHALL 維持不變、命令 SHALL 正常結束（exit 0）
