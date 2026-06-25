# stage2-noise-governance Specification

## Purpose
定義 knowledge 噪音的判準（classifier）、產生端過濾、回溯 prune 與稽核 manifest，於產生端阻斷結構/空殼/placeholder slice、並可回溯 hard-delete 既有噪音，同時避免誤刪真實知識。
## Requirements
### Requirement: 以 body 內容判定 noise

系統 SHALL 提供純函式 `classify_noise(frontmatter, body)`，回傳 `(is_noise, reason)`，且判定**僅依 body 內容**，不依賴 frontmatter 的 `atom_title` / `title` / `project`。判定規則依序為：(1) **structural-echo**——(a) body 第一行為 importer-exclusive 結構 heading（`## CWD` / `## Source` / `## Prompts` / `## Touched files` / `## Referenced artifacts`）或 session metadata 區塊（`#{1,6} Session Metadata|Information`）→ **無條件** echo（這些段落名永遠不是合法的獨立知識原子標題）；(b) body 第一行為 `## Summary`（真筆記常見）→ 僅當散文行（非標題、非清單）≤1 時才 echo；(2) body **開頭附近**（前 12 字內）含 `尚未收到您的具體需求` / `目前尚未收到` / `(無內容)`，或本體僅 `- (none)` / `(unknown)` → `placeholder`；(3) body 去除標題行（`#`..）與空白行後無實質內容（涵蓋純標題片段如 `# Session <uuid>` 與真正空白）→ `empty`；皆不命中則非 noise。判定 SHALL 為 content-based，MUST NOT 以字元長度門檻判定。因 classifier 同時用於 hard-delete 路徑，規則 SHALL 為 deletion-grade：`## Summary` 的 ≤1 散文行 guard 與 placeholder 的開頭偵測，避免誤刪「以 `## Summary` 開頭但有多段真內容」或「引用 placeholder 字串」的真筆記。

#### Scenario: importer-exclusive 結構段落無條件判為 noise

- **WHEN** slice body 第一行為 `## CWD`、`## Prompts`、`## Source`、`## Touched files`、`## Referenced artifacts`，或為 `Session Metadata` / `Session Information` 區塊（不論其後內容多寡）
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `structural-echo:<section>`

#### Scenario: `## Summary` 僅在淺內容時判為 noise

- **WHEN** slice body 第一行為 `## Summary` 且散文行 ≤1
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `structural-echo:Summary`

#### Scenario: 純標題片段與 placeholder 判為 noise

- **WHEN** slice body 去除標題行與空白後無實質內容（如 `# Session <uuid>`），或開頭附近含 placeholder 字串
- **THEN** `classify_noise` SHALL 回 `is_noise=True` 且 `reason` 為 `empty` 或 `placeholder`

#### Scenario: 真實短內容不因長度被誤判

- **WHEN** slice body 為非標題、非 placeholder 的真實短句（例如 30 字的技術結論）
- **THEN** `classify_noise` SHALL 回 `is_noise=False`（判定 MUST NOT 依字元長度門檻）

#### Scenario: 以 `## Summary` 開頭但有多段真內容者保留

- **WHEN** slice body 第一行為 `## Summary`，但其後含 ≥2 行真實散文
- **THEN** `classify_noise` SHALL 回 `is_noise=False`（非 structural-echo，防 hard-delete 誤刪）

#### Scenario: 引用 placeholder 字串的真筆記保留

- **WHEN** slice body 為真內容，僅在中段引用 placeholder 字串（非開頭）
- **THEN** `classify_noise` SHALL 回 `is_noise=False`

#### Scenario: 有真內容者保留（精度防誤刪）

- **WHEN** slice 的 `atom_title` 為 `untitled` 或 `project` 為 username fallback，但 body 含足夠真實內容（例如 checklist、技術結論）
- **THEN** `classify_noise` SHALL 回 `is_noise=False`

### Requirement: 產生端過濾防止噪音新生

atomize 的 promote pass SHALL 在 slice 通過 frontmatter 驗證後、寫入 knowledge 前，對每個 slice 套用 `classify_noise`；判為 noise 者 MUST NOT 寫入 knowledge 層、MUST NOT 建立 semantic relation，並 SHALL 計入結果 summary 的 `noise_dropped`。source fragment 的 archive 與 session 的 promoted 標記 SHALL 不受影響。預期內的 noise 丟棄 MUST NOT 計入健康訊號（`warnings` / summary `skipped`），以免正常的過濾被誤判為 degraded（partial）；診斷細節改以 log 記錄。

#### Scenario: noise slice 被產生端丟棄

- **WHEN** promoter 對某 session 產出一個 body 為結構段落 echo 的 slice
- **THEN** 該 slice MUST NOT 出現在 knowledge 層，且 summary `noise_dropped` SHALL 反映被丟棄數，source fragment SHALL 仍被 archive

#### Scenario: noise 丟棄不汙染健康訊號

- **WHEN** 某 run 僅因 noise 過濾而丟棄 slice、無其他異常
- **THEN** summary `skipped` SHALL 為 0 且 `warnings` MUST NOT 含 noise 丟棄條目（使 dream 健康判定為 clean）

#### Scenario: 乾淨 slice 正常寫入

- **WHEN** promoter 產出 body 為真實萃取內容的 slice
- **THEN** 該 slice SHALL 正常寫入 knowledge 並建立其 relation

### Requirement: 回溯 prune 既有噪音

系統 SHALL 提供 `psc memory knowledge prune-noise` 子命令掃描 `knowledge/**.md`（排除 `*-moc.md`），對每檔以 `classify_noise` 判定。預設 `--dry-run` MUST NOT 修改任何檔，僅列出將刪清單與 reason 統計。`--apply` SHALL hard delete 命中檔並重建 MOC。命令 SHALL 一律輸出稽核 manifest 至 `runtime/ledger/prune-<now>.jsonl`（每行含 slice_id / project / path / reason / status）。`--apply` SHALL 先持久化「planned」manifest 後才執行任何 unlink，刪除完成再以 atomic replace 重寫最終狀態；確保任何後續寫入失敗都不致留下無紀錄的刪除。

#### Scenario: dry-run 不動檔

- **WHEN** 執行 `prune-noise --dry-run`
- **THEN** 命令 SHALL 列出將刪 slice 與 reason 統計，且 knowledge 層任何檔 MUST NOT 被刪除或修改

#### Scenario: apply 刪噪音並保留乾淨 slice

- **WHEN** 執行 `prune-noise --apply`，knowledge 同時含噪音與乾淨 slice
- **THEN** 命中 noise 的檔 SHALL 被 hard delete、乾淨 slice SHALL 全數保留、manifest SHALL 記錄每筆刪除、MOC SHALL 重建且不含已刪 slice

#### Scenario: 刪除前已有 durable manifest

- **WHEN** `prune-noise --apply` 開始刪除任一檔
- **THEN** 該次的 planned manifest SHALL 已先寫入 `runtime/ledger/`，使任一後續失敗都不致留下無稽核紀錄的刪除

#### Scenario: 單檔刪除失敗不中止整體

- **WHEN** `--apply` 過程中某檔刪除失敗
- **THEN** 該筆 SHALL 以 `status=error` 記入 manifest、命令 SHALL 跳過該檔並續處理其餘檔

