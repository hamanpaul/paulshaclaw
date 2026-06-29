## MODIFIED Requirements

### Requirement: usage 訊號擷取純函式

系統 SHALL 於 `paulshaclaw/memory/usage.py` 保留純函式 `extract_offered(brief)`（從含 `[[stem--sl-id|title]]` wikilink 的文字抽 `(slice_id, title)`），供相容與工具用途。`extract_cited` / `extract_matched`（逐字 `sl-id` 回吐 / 標題逐字命中）SHALL 標記為 **deprecated、非規範**：二者 MUST NOT 再作為 `used` 主訊號（主訊號改為 read-based 歸因，見 `stage2-memory-read-attribution`）；保留僅為向後相容，得於後續另案移除。所有保留函式 MUST 為純函式、對畸形輸入回空集合而不丟例外。

#### Scenario: extract_offered 仍可從 wikilink 抽 offered
- **WHEN** 對含 `[[foo--sl-abc...|標題]]` 的文字呼叫 `extract_offered`
- **THEN** 回傳含 `(sl-abc..., 標題)` 的清單

#### Scenario: cited/matched 不再驅動 used 主訊號
- **WHEN** 計算某 session 的 `used`
- **THEN** 系統 SHALL 採 read-based 歸因事件，MUST NOT 以 `extract_cited`/`extract_matched` 作為 used 來源

### Requirement: usage 查詢 CLI

系統 SHALL 提供 `psc memory usage`（`--memory-root`、`--since`、`--json`）**僅讀 `memory_usage.jsonl`** 聚合出每 slice 的 `offered_count / read_count / last_read`（依 read 降冪）與彙總（總 session、平均每 session read、never-read 數＝offered 過但 read=0）。`read_count` SHALL 來自 read-based `used` 事件（`source:"read"`）。即使 `runtime/wakeup/*.json` 全不存在，報告 SHALL 正確（ledger 自足）。

#### Scenario: offered-but-unread 計入 never-read 且報告自足
- **WHEN** 某 slice 在 ledger 多次 offered 但從未有 read 事件，且 wakeup 檔已不存在
- **THEN** `memory usage` SHALL 列出該 slice（offered_count>0、read_count=0）並計入 never-read 彙總

#### Scenario: read 事件計入 read_count
- **WHEN** ledger 含某 slice 的 `source:"read"` used 事件
- **THEN** 該 slice 的 `read_count` SHALL ≥1 且 `last_read` SHALL 反映最近事件時間

## REMOVED Requirements

### Requirement: SessionStart 記錄 offered 並提示引用

**Reason**: 16-hex 引用前言（要 agent 回吐 `[[sl-id]]`）驅動假 0（RCA：6 session 全 cited:[]），且 SessionStart 在任務未知前注入無法做任務相關性。
**Migration**: 引用前言移除；offered 改由 `stage2-memory-prompt-retrieval` 於 UserPromptSubmit per-prompt 記錄（含 sl_id+絕對路徑）。SessionStart brief 改為極簡 orientation（見 `stage2-memory-readback`），不再寫 session-wide offered 集。

### Requirement: claude SessionEnd 擷取 used 並寫 durable ledger

**Reason**: 逐字 `extract_cited`（要 agent 貼 16-hex id）/ `extract_matched`（標題逐字命中、47% 標題為佔位 `# AGENTS.md instruct`、~17% CJK 被砍斷）結構上無法偵測自然的 paraphrase 使用，產生假 0 為儀器地板。
**Migration**: `used` 改由 `stage2-memory-read-attribution` 的 PostToolUse(Read) read-based 事件記錄（`source:"read"`），no-op/短 session 因「無 prompt→無 offered→無 used」自然不再產假 0 列。
