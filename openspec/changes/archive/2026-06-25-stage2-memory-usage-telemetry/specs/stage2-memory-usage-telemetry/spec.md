# stage2-memory-usage-telemetry

記憶消費端 usage 訊號的擷取（offered / cited / matched）、持久化 ledger 與查詢 CLI。

## ADDED Requirements

### Requirement: usage 訊號擷取純函式

系統 SHALL 提供純函式模組 `paulshaclaw/memory/usage.py`，包含 `extract_offered(brief)` 從 wake-up brief 的 `[[stem--sl-id|title]]` 抽出 `(slice_id, title)` 清單；`extract_cited(assistant_text, offered_ids)` 回傳 assistant 文字中顯式出現（`[[sl-id]]` 或裸 `sl-id`）且 ∈ offered_ids 的 id 集合；`extract_matched(assistant_text, offered)` 回傳 assistant 文字命中 offered slice 標題（標題 strip 後 ≥ 8 字才比對）且未被 cited 涵蓋的 id 集合。三函式 MUST 為純函式、對畸形輸入回空集合而不丟例外。

#### Scenario: 從 brief 抽 offered

- **WHEN** 對含 `[[foo--sl-abc...|標題]]` 的 brief 呼叫 `extract_offered`
- **THEN** 回傳含 `(sl-abc..., 標題)` 的清單

#### Scenario: cited 認顯式引用、過濾非 offered

- **WHEN** assistant 文字含 `[[sl-x]]`（∈ offered）與 `[[sl-z]]`（∉ offered）
- **THEN** `extract_cited` SHALL 回傳 `{sl-x}`，不含 `sl-z`

#### Scenario: matched 認標題、排除短標題與已 cited

- **WHEN** assistant 文字出現某 offered slice 的 ≥8 字標題，且該 slice 未被 cited
- **THEN** `extract_matched` SHALL 回傳該 slice id；標題 < 8 字或已 cited 者 MUST NOT 列入

### Requirement: SessionStart 記錄 offered 並提示引用

SessionStart 的 wake-up 共用邏輯 SHALL 在 brief 非空時前置一段引用前言（提示 agent 用到記憶時標註 `[[sl-id]]`），並在算出 brief 後將 offered slice（id + title）原子寫入 `runtime/wakeup/<tool>__<sid>.json`。offered 寫入或前言失敗 MUST NOT 影響 brief 輸出（best-effort）。此行為對三家 agent 共用。

#### Scenario: offered 落地且帶引用前言

- **WHEN** SessionStart 對某可解析 project 算出非空 brief
- **THEN** brief SHALL 含引用前言，且 `runtime/wakeup/<tool>__<sid>.json` SHALL 含該 brief 的 offered slice id+title

#### Scenario: brief 為空不加前言

- **WHEN** project 無法解析或 brief 為空
- **THEN** MUST NOT 加引用前言、MUST NOT 寫 offered 檔

### Requirement: claude SessionEnd 擷取 used 並寫 durable ledger

claude SessionEnd SHALL 讀該 session 的 offered 檔與 `transcript_path`（僅取 role=assistant 訊息文字，排除被注入的 brief），以 usage 函式算出 cited 與 matched，並 append 一筆 event 至 `runtime/ledger/memory_usage.jsonl`。event MUST 持久化 **offered slice id 陣列**（非僅數量），使後續查詢與 decay 分析只需讀 ledger、不依賴可被清理的 wakeup 檔。缺 offered 檔或 transcript MUST NOT 寫 event 且 MUST NOT 報錯（hook 照常 exit 0、既有擷取/import 不受影響）。

#### Scenario: 寫出含 offered id 陣列的 usage event

- **WHEN** SessionEnd 有 offered 檔且 transcript 含 assistant 引用
- **THEN** `memory_usage.jsonl` SHALL 新增一筆含 `offered`(id 陣列) / `cited` / `matched` / `session_id` / `project` / `ts` 的 event

#### Scenario: 缺輸入時不寫且不報錯

- **WHEN** offered 檔不存在，或 payload 無 `transcript_path` / 檔不存在
- **THEN** MUST NOT 寫 event、hook SHALL exit 0，既有擷取/import 不受影響

### Requirement: usage 查詢 CLI

系統 SHALL 提供 `psc memory usage`（`--memory-root`、`--since`、`--json`）**僅讀 `memory_usage.jsonl`** 聚合出每 slice 的 `offered_count / cited_count / matched_count / last_used`（依 cited 降冪）與彙總（總 session、平均每 session cited/matched、never-used 數＝offered 過但 cited+matched=0）。即使 `runtime/wakeup/*.json` 全不存在，報告 SHALL 正確。

#### Scenario: offered-but-unused 計入 never-used 且報告自足

- **WHEN** 某 slice 在 ledger 多次 offered 但從未 cited/matched，且 wakeup 檔已不存在
- **THEN** `memory usage` SHALL 列出該 slice（offered_count>0、cited+matched=0）並計入 never-used 彙總
