## ADDED Requirements

### Requirement: Project key rekey migration

Stage 2 SHALL 提供一次性 rekey 遷移工具：模組 `paulshaclaw.memory.rekey` 與 CLI `memory knowledge rekey --memory-root <root> --from <old-key> --to <slug>`。工具 MUST 僅選取 frontmatter `memory_layer: knowledge` 且 `project` 與 `<old-key>` 嚴格相等的 slice（略過 `-moc.md`）。`--to` MUST 為 path-safe slug（依 `atomizer/config.py::is_safe_path_component`，不得含 `/`），違反時 CLI MUST 以 exit code 2 拒絕且不產生任何副作用。預設（未帶 `--apply`）為 dry-run：MUST 產出審計 manifest `runtime/ledger/rekey-<now>.jsonl`（原子寫入）且 MUST NOT 改動任何 knowledge 檔案。`--apply` 時每筆候選 MUST 改寫 frontmatter `project` 為新 slug、將檔案搬移至 `knowledge/<sanitized-slug>/`（`sanitize_project_component`），並保留 `slice_id` 與 body；有任何成功筆數時 MUST 觸發 `moc/runner.py::run_moc` 重建 MOC 與 retrieval index。工具 MUST NOT 直接讀寫 `runtime/indexes/retrieval.db`。

#### Scenario: dry-run 產 manifest 不動檔案

- **WHEN** 對含 1 筆 `project: github.com/hamanpaul/testpilot` slice 的 memory root 執行 rekey（`--to testpilot`，未帶 `--apply`）
- **THEN** `runtime/ledger/rekey-<now>.jsonl` MUST 存在且該筆 status 為 `dry-run`、含 `from`/`to`/`path`/`target` 欄位
- **THEN** 原檔案 MUST 原地保留且 frontmatter `project` 不變

#### Scenario: apply 搬檔、改 frontmatter、重建 MOC

- **WHEN** 對同一 memory root 執行 rekey `--apply`
- **THEN** 檔案 MUST 出現在 `knowledge/testpilot/` 下且原路徑消失
- **THEN** frontmatter `project` MUST 等於 `testpilot`，`slice_id` 與 body MUST 逐字不變
- **THEN** manifest 該筆 status MUST 為 `rekeyed`，且 `knowledge/testpilot-moc.md` MUST 存在（run_moc 已觸發）

#### Scenario: 目標檔已存在時 conflict fail-safe

- **WHEN** 目的地 `knowledge/<slug>/` 已存在同名檔案
- **THEN** 該筆 MUST 記為 `conflict`，source 檔案（含 frontmatter）MUST 完全不動

#### Scenario: 不安全 slug 被拒絕

- **WHEN** `--to` 含 `/`（如 `a/b`）
- **THEN** CLI MUST 回傳 exit code 2 且 MUST NOT 產生 manifest 或改動任何檔案

#### Scenario: apply 收尾清空的舊 key 目錄與孤兒 moc

- **WHEN** apply 成功搬走舊 key 目錄下全部檔案，且 `knowledge/<sanitized-old-key>-moc.md` 存在
- **THEN** 清空的 `knowledge/<sanitized-old-key>/` 目錄 MUST 被移除
- **THEN** 孤兒 `<sanitized-old-key>-moc.md` MUST 被移除

### Requirement: Fixed-list prune mode

`memory knowledge prune-noise` SHALL 支援 `--paths <file>` 固定清單模式：清單檔每行一個絕對路徑，`#` 開頭與空白行忽略。此模式 MUST 與 `--instruction-root`、`--project` 互斥（同時給定 → exit code 2、零副作用）。刪除範圍 MUST 恰為清單內檔案——清單即權威，不需 `classify_noise` 同意，manifest reason MUST 為 `listed`。驗證 MUST fail-closed：任一清單路徑不存在、resolve 後不在 `<memory-root>/knowledge/` 之下、為 `-moc.md`、或 frontmatter 非 `memory_layer: knowledge` 時，MUST 以 exit code 2 中止且 MUST NOT 刪除任何檔案。清單全部有效時 MUST 在任何 unlink 之前先寫 manifest，apply 後更新各筆狀態並重建 MOC（`build_mocs`）。

#### Scenario: 只刪清單內檔案

- **WHEN** 清單僅含 1 筆 untitled slice 路徑，而同專案另有 1 筆可判 noise 但未列清單的 slice，執行 `--paths <file> --apply`
- **THEN** 清單內檔案 MUST 被刪除（即使 `classify_noise` 不會判它為 noise）
- **THEN** 未列清單的 noise 檔與其他真筆記 MUST 全部保留
- **THEN** manifest MUST 恰含清單筆數列、reason 全為 `listed`

#### Scenario: 清單超出範圍即整批中止

- **WHEN** 清單含一個不存在的路徑或一個位於 `knowledge/` 之外的檔案
- **THEN** 命令 MUST 回傳 exit code 2
- **THEN** 清單內其餘（本身有效的）檔案 MUST NOT 被刪除

#### Scenario: dry-run 不刪

- **WHEN** 以 `--paths <file> --dry-run` 執行
- **THEN** manifest MUST 產出且各筆 status 為 `dry-run`，所有檔案 MUST 保留

#### Scenario: 與掃描模式互斥

- **WHEN** 同時給定 `--paths` 與 `--project`（或 `--instruction-root`）
- **THEN** 命令 MUST 回傳 exit code 2 且 MUST NOT 產生 manifest

### Requirement: Janitor hygiene lint for untitled and raw-remote keys

janitor scan SHALL 對 knowledge records 執行 read-only lint：frontmatter `title` 等於 `untitled` → rule `title-untitled`；frontmatter `project` 含 `/`（raw-remote key）→ rule `raw-remote-key`。lint MUST NOT 修改任何檔案、MUST NOT 寫入 lifecycle 事件（告警不自動改）。`run_scan` 回傳的 summary MUST 含 `lint` 欄位 `{"untitled": <N>, "raw_remote_key": <M>}`（經 dream orchestrator 的 summary passthrough 落入 dream ledger `passes.janitor`），且每筆 finding MUST 以 `lint:<rule>: <path> (project=<key>)` 形式 append 至 warnings。lint 結果 MUST deterministic（按 record_id 排序）。乾淨樹 MUST 回傳零 counts 且無 `lint:` 開頭的 warnings。

#### Scenario: untitled 與 raw-remote key 同時告警

- **WHEN** knowledge 樹含 1 筆 `title: untitled` 且 `project: github.com/hamanpaul/testpilot` 的 slice，執行 janitor scan
- **THEN** `summary["lint"]` MUST 等於 `{"untitled": 1, "raw_remote_key": 1}`
- **THEN** warnings MUST 含 2 筆 `lint:` 開頭的訊息
- **THEN** 該 slice 檔案 MUST 原封不動、lifecycle ledger MUST 無 lint 相關事件

#### Scenario: 乾淨樹零告警

- **WHEN** knowledge 樹所有 slice 都有真標題且 project 為短 slug
- **THEN** `summary["lint"]` MUST 等於 `{"untitled": 0, "raw_remote_key": 0}` 且無 `lint:` warnings

#### Scenario: 告警進 dream ledger

- **WHEN** dream run 的 janitor pass 掃到 lint findings
- **THEN** dream ledger 該輪記錄的 `passes.janitor.lint` MUST 帶有非零 counts（經既有 summary passthrough，無需 orchestrator 改動）
