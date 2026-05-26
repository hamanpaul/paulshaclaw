## Why

PaulShiaBro 的 Telegram 非指令對話目前直接呼叫 vLLM Gemma4 HTTP API（無狀態、無上下文記憶）。需要替換為 `claude-gemma4` wrapper——一個透過 Claude Code CLI 驅動本地 Gemma4 的互動式 session，具備上下文維持能力，並能透過 bro skill 主動回覆 Telegram。同時將散落在 `~/.local/bin/` 的 wrapper 和 proxy 收納進 repo 統一管理。

## What Changes

- **新增 `/agent` Telegram 指令**：支援 `start`、`startf`、`stop`、`status` 子命令，透過 tmux 原語管理 claude-gemma4 session 的生命週期
- **修改非指令對話路由**：從直接呼叫 OpenAI-compatible HTTP API 改為偵測 claude-gemma4 process → tmux send-keys 轉發 → bro skill 回覆
- **收納 claude-gemma4 到 repo**：wrapper script、proxy server、settings template 搬入 `scripts/` 和 `config/`
- **BREAKING**：移除 `paulshaclaw/chat/` 模組（openai.py、config.py、backend.py）及 `OPENAI_*` 環境變數依賴
- **移除原有對話 log 系統**：listener.py 中與 chat backend 相關的 IN/OUT log

## Capabilities

### New Capabilities
- `agent-command`: Telegram `/agent` 指令與 claude-gemma4 tmux pane 生命週期管理
- `agent-conversation-routing`: 非指令對話透過 process 偵測 + tmux send-keys 路由到 claude-gemma4 pane

### Modified Capabilities
- `stage1`: 移除 chat backend 依賴，對話路由改為 agent pane 轉發

## Impact

- **程式碼**：`paulshaclaw/chat/` 整個刪除；`daemon.py`、`telegram.py`、`listener.py` 修改；`commands.json` 新增指令
- **腳本**：新增 `scripts/claude-gemma4`、`scripts/claude-gemma4-proxy`；`config/claude-gemma4-settings.json`
- **依賴**：移除舊 chat backend 的 `OPENAI_BASE_URL`/`OPENAI_MODEL` provider 設定；`claude-gemma4` runtime 改讀 `PSC_CLAUDE_GEMMA4_API_KEY`（`OPENAI_API_KEY` 僅保留相容 fallback），並新增 `claude-gemma4` CLI 可用性前提
- **測試**：需更新現有 chat backend 相關測試，新增 agent command handler 測試
