## Why

三家 agent 的記憶管線雙向都接好（擷取 + wake-up 注入），但**注入後 agent 有沒有讀/用，完全沒有訊號**（#148）。沒有消費端訊號就量不出記憶 ROI、無法調 relevance、janitor decay 也缺真實依據。需建立最小 usage 訊號管道：知道每個 session 被 offered 了哪些 slice、agent 實際 used（引用/命中）了哪些。

## What Changes

- 新增純函式 `paulshaclaw/memory/usage.py`：`extract_offered`（從 brief 抽 slice id+title）、`extract_cited`（assistant 顯式 `[[sl-id]]`）、`extract_matched`（assistant 文字命中 offered 標題，≥8 字）。
- SessionStart（共用 `_wakeup_common`，三家）：brief 前置引用前言；算出 brief 後寫 `runtime/wakeup/<tool>__<sid>.json`（offered id+title）。
- claude SessionEnd：讀 offered + transcript（只掃 assistant role）→ cited + matched → append `runtime/ledger/memory_usage.jsonl`（event 內 `offered` 為 id 陣列，self-sufficient）。
- 新 CLI `psc memory usage`：僅讀 ledger → per-slice offered/cited/matched/last_used + 彙總（含 never-used）。

## Capabilities

### New Capabilities
- `stage2-memory-usage-telemetry`: 記憶消費端 usage 訊號的擷取（offered/cited/matched）、持久化 ledger 與查詢 CLI。

### Modified Capabilities
<!-- 無 spec-level 行為變更：wake-up 注入與擷取的既有契約不變，本 change 只增掛 telemetry。 -->

## Impact

- 程式：新增 `paulshaclaw/memory/usage.py`；改 `~/.agents/memory/hooks/_wakeup_common.py`（共用，repo 對應 `paulshaclaw/memory/hooks/_wakeup_common.py`）、`claude_session_end.py`；`paulshaclaw/memory/cli.py` 加 `memory usage`。
- 資料：新增 `runtime/wakeup/<tool>__<sid>.json`（傳遞媒介，可清理）與 `runtime/ledger/memory_usage.jsonl`（durable）。
- 範圍：claude-only 的 used（codex/copilot 先只 offered）；不接 relevance/decay（後續）。
- 部署：hooks 自 repo editable 載入，毋須重裝；新 session 即生效。
