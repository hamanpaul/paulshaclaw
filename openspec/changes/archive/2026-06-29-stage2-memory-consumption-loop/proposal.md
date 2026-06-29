## Why

Stage 2 記憶生產端已穩定運轉（每小時 dream、229 筆 knowledge、747 測試綠），但消費端 telemetry 6 筆 session 全 `cited:[]/matched:[]`。6-agent RCA workflow 證實 0 引用是過度決定：(1) brief 從不把 slice 內文交給模型、連結 `[[stem]]` 在 Claude Code 打不開；(2) 偵測器只認逐字 16-hex id / 標題；(3) 檢索在 SessionStart 任務未知時建構、只吃 project+時間；(4) 55% 池內容是已在 system prompt 的 AGENTS.md 片段。記憶被產出卻無法被取用、也無法被誠實量測——本變更把死迴路換成活迴路。

## What Changes

- 新增 **UserPromptSubmit 任務條件式檢索**：用當前 prompt 跑既有 bm25 ranker（`search.py`），注入 top-k 短清單（標題·一行摘要·**絕對路徑**），附「相關項用 Read 取全文」提示。
- 新增 **PostToolUse(Read) 讀取歸因**：agent native Read 被推送的 knowledge 路徑時，以「讀取=使用」記精準 `used` 事件。
- **池端/index 排除噪音（新）**：`build_index`（`search.py`）與 slim brief 對 `classify_noise` 命中者（doc-fragment / structural-echo / empty / placeholder）做 defense-in-depth 排除，使未及 prune 的殘留噪音也不會進短清單；另對 `canary-fixture`/`review-record` 做**非刪除級**池排除。
- **清現存殘留（操作面，重用既有 `prune-noise`）**：既有 doc-fragment 產生端丟棄與 `psc memory knowledge prune-noise` 已具備；殘留 ~127 筆未清屬 corpus scoping 操作缺口。本變更以既有 `prune-noise`（`--project` scoped corpus、`--dry-run` gated、人核 manifest + 備份）清除，**不重造分類或 CLI**。
- SessionStart brief 瘦成極簡 orientation；移除 16-hex `CITATION_PREAMBLE`；offered 改 per-prompt 記錄。
- **BREAKING（內部 telemetry 契約）**：退役 SessionEnd 逐字 `extract_cited`/`extract_matched` 主訊號，`used` 改 read-based 事件；`psc memory usage` 改讀 read 計數。

## Capabilities

### New Capabilities
- `stage2-memory-prompt-retrieval`: UserPromptSubmit 時依當前 prompt 做 bm25 檢索、relevance gate、注入 top-k 短清單（含可開啟絕對路徑）、per-prompt 記 offered。
- `stage2-memory-read-attribution`: PostToolUse(Read) 偵測 knowledge 路徑讀取、對齊 session offered、append read-based `used` 事件（best-effort、Claude-only）。

### Modified Capabilities
- `stage2-memory-readback`: SessionStart brief 由 project MOC dump 改為極簡 orientation；移除 16-hex 引用前言；不再於 SessionStart 寫大 offered 集。
- `stage2-memory-usage-telemetry`: `used` 主訊號由逐字 cited/matched 改為 read-based 事件；event/CLI 改記 read_count/last_read/never-read。
- `stage2-noise-governance`: 新增 index/offered-pool 對 `classify_noise` 命中者的 defense-in-depth 排除，及 `canary-fixture`/`review-record` 非刪除級池排除。既有 doc-fragment 分類、產生端丟棄、`prune-noise` CLI **重用不改**（清殘留為操作面）。

## Impact

- 程式碼：`paulshaclaw/memory/` 之 `hooks/`（新增 `claude_user_prompt_submit.py`、`claude_post_tool_use.py`、共用 `_shortlist_common.py`；改 `_wakeup_common.py`）、`wakeup/builder.py`（slim brief + 池排除）、`moc/search.py`（build_index 排除 noise；可能擴 search 回傳 path）、`usage.py`/`usage_ledger.py`、`cli.py`(usage)。既有 `noise.py`/`prune-noise`/atomize promote 過濾 **重用不改**。
- 設定：`~/.claude/settings.json` 增掛 UserPromptSubmit（與 codegraph 並存）+ PostToolUse(Read) memory hook；hooks 須 install.sh 重新同步到 `~/.agents/memory/hooks/`。
- 資料：`runtime/ledger/`（offered.jsonl、memory_usage.jsonl 格式演進）、`runtime/wakeup/<tool>__<sid>.offered.json`；live `knowledge/` 將刪除 ~127 筆噪音（不可逆，`~/.agents` 非 git）。
- 相依：無新外部相依（重用 sqlite FTS5、現有 search/prune/noise 機制）。
- 範圍邊界：不改 hourly dream/atomize/janitor/MOC 主流程；codex/copilot 的 read 歸因暫不實作（仍收短清單）。
