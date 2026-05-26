## Context

PaulShiaBro Stage 1 的 Telegram bot 目前透過 `paulshaclaw/chat/` 模組直呼 vLLM OpenAI-compatible API 處理非指令對話。此路徑無狀態、無上下文記憶。

使用者已在 `~/.local/bin/` 建立 `claude-gemma4` wrapper——用 Claude Code CLI 驅動本地 Gemma4 模型，附帶 proxy 注入 `enable_thinking=false`，具備 session 上下文。現在要把這套工具收進 repo，並透過 Telegram `/agent` 指令管理 tmux pane 生命週期。

相關檔案現況：
- `paulshaclaw/bot/telegram.py` — TelegramCommandRouter，路由指令 vs 非指令
- `paulshaclaw/core/daemon.py` — PaulShiaBroDaemon，指令 handler 註冊
- `paulshaclaw/core/commands.json` — 指令定義
- `paulshaclaw/chat/` — 即將移除的 OpenAI chat backend
- `paulshaclaw/bot/listener.py` — Telegram long-polling + IN/OUT log
- `scripts/start.sh` — 服務啟動腳本
- `custom-skills/paulshiabro-telegram-reply/` — bro skill (reply_bridge.py)

## Goals / Non-Goals

**Goals:**
- 透過 `/agent start|startf|stop|status` 管理 claude-gemma4 session 的完整生命週期
- 非指令對話在 agent 運行時透過 tmux send-keys 轉發，claude-gemma4 透過 bro skill 主動回覆
- 將 claude-gemma4 wrapper、proxy、settings template 收納進 repo
- 完全移除 `paulshaclaw/chat/` 模組及 OPENAI_* 環境變數依賴

**Non-Goals:**
- 不實作多 agent 並行（一次只有一個 claude-gemma4 session）
- 不持久化 agent 狀態（daemon 重啟 = agent 需要重新啟動）
- 不改動 bro skill 本身的邏輯
- 不改動 cockpit TUI 介面

## Decisions

### D1：Agent 生命週期——tmux 原語而非新模組

**選擇**：所有 agent 管理操作直接用 `tmux split-window`、`send-keys`、`list-panes` 等原語，handler 寫在 daemon.py 內。

**替代方案**：建立獨立 `paulshaclaw/agent/` 模組封裝 AgentManager 類別。

**理由**：操作本質就是幾條 tmux 指令加 process 偵測，封裝反而多一層抽象。daemon 已有 `_send_to_pane` 先例，風格一致。

### D2：Pane 建立方式——從 cockpit pane 水平分割

**選擇**：`tmux split-window -h -t $COCKPIT_PANE` 在 cockpit 旁邊建新 pane。

**理由**：使用者明確要求「在 TUI 所在 pane 中新切一個 pane（橫式）」。cockpit pane ID 透過 `TMUX_PANE` 環境變數或 `--cockpit-pane` 參數取得（start.sh 已有此機制）。

### D3：Agent 存活偵測——process tree 掃描

**選擇**：不依賴 daemon 記憶的 `_agent_pane_id`，每次操作時掃描 tmux panes 的 process tree 找 `claude-gemma4` process。

**流程**：
1. `tmux list-panes -a -F '#{pane_id} #{pane_pid}'`
2. 對每個 pane_pid 用 `pgrep -P $pid -a` 或 `ps --ppid` 檢查子程序樹是否含 `claude-gemma4`
3. 找到 → 回傳該 pane_id + process 資訊；找不到 → stopped

**理由**：使用者要求先看 process 再找 pane。此方式也能在 daemon 重啟後自動重新發現已存在的 agent。

**daemon 仍保留 `_agent_pane_id` hint**：start 時記住，用於加速 send-keys（不需每次全掃），但不作為唯一判據。

### D4：非指令對話路由

**選擇**：
1. process tree 偵測 claude-gemma4 是否存活
2. 存活 → 透過 tmux send-keys 送訊息到 agent pane → 同步回 Telegram `"…"`
3. 不存活 → 回覆 fallback 訊息 `"agent 未啟用，請使用 /agent start"`

**送進 pane 的格式**：`[user:<user_id>] <text>`，讓 claude-gemma4 的 CLAUDE.md 指示它解析 user_id 並用 `--source-user-id` 回覆。

### D5：claude-gemma4 收納位置

**選擇**：
- `scripts/claude-gemma4` — wrapper shell script
- `scripts/claude-gemma4-proxy` — Python proxy server
- `config/claude-gemma4-settings.json` — Claude Code settings template

**路徑調整**：wrapper 內的 `GEMMA_PROXY` 改為 `$REPO/scripts/claude-gemma4-proxy`；`GEMMA_CONFIG_DIR` 保持 `~/.claude-gemma4`（runtime state 不進 repo）。

### D6：移除 chat 模組的邊界

**選擇**：完整刪除 `paulshaclaw/chat/` 目錄（`__init__.py`、`openai.py`、`config.py`、`backend.py`）。`TelegramCommandRouter` 不再接收 `chat_backend` 參數。`listener.py` 不再 import `create_chat_backend`。

## Risks / Trade-offs

- **[Agent process 偵測假陽性]** → 如果使用者在其他 pane 手動跑 claude-gemma4，會被誤認為 bot 管理的 agent。Mitigation：可在 wrapper 啟動時設 pane title 為特定標記，偵測時同時比對 title。初版先不做，遇到再加。
- **[tmux 不可用]** → 如果不在 tmux 環境中（如 CI），`/agent start` 會失敗。Mitigation：handler 內檢查 tmux 可用性，不可用時回報錯誤。與 tmate handler 做法一致。
- **[claude-gemma4 回覆延遲]** → LLM 推理可能需要數十秒，Telegram 使用者只看到 `"…"` 。Mitigation：可接受，使用者理解 LLM 回覆有延遲。
- **[BREAKING: 移除 chat backend]** → 任何依賴 `paulshaclaw.chat` 的外部程式碼會壞。Mitigation：此 repo 無外部消費者，只需更新內部測試。
